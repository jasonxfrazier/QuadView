"""Validate browser destinations without making network requests."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit

_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_HOST_WITH_PORT = re.compile(r"^[^:/?#]+:[0-9]+(?:[/?#]|$)")
_DNS_LABEL = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\Z")
_NON_WEB_SCHEMES = {
    "about", "blob", "chrome", "data", "file", "ftp", "ftps", "javascript",
    "mailto", "resource", "sms", "tel", "vbscript", "view-source", "ws", "wss",
}


def normalize_url(value: str) -> str:
    """Return an HTTP(S) URL, adding HTTPS only when no scheme was supplied.

    Host names are checked syntactically, including IDNA names. No DNS lookup
    occurs, so intranet hosts and destinations that are currently offline work.
    """
    if not isinstance(value, str) or not value:
        raise ValueError("Enter a website URL.")
    if any(char.isspace() or unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("URLs cannot contain whitespace or control characters.")
    if "\\" in value:
        raise ValueError("Use forward slashes in a website URL.")

    scheme = _SCHEME.match(value)
    if value.startswith("//"):
        normalized = "https:" + value
    elif scheme and scheme.group()[:-1].lower() in {"http", "https"}:
        if not value[len(scheme.group()):].startswith("//"):
            raise ValueError("HTTP and HTTPS URLs must include // after the scheme.")
        normalized = value
    elif scheme and (
        scheme.group()[:-1].lower() in _NON_WEB_SCHEMES
        or not _HOST_WITH_PORT.match(value)
    ):
        raise ValueError("Only http:// and https:// website URLs are supported.")
    else:
        normalized = "https://" + value

    try:
        parts = urlsplit(normalized)
        hostname = parts.hostname
        port = parts.port
    except ValueError as exc:
        raise ValueError("The URL contains an invalid host or port.") from exc
    if parts.scheme.lower() not in {"http", "https"} or not hostname:
        raise ValueError("Enter a valid HTTP or HTTPS website address.")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URLs containing usernames or passwords are not supported.")
    if parts.netloc.endswith(":") or port == 0:
        raise ValueError("The URL port must be a number from 1 to 65535.")

    if parts.netloc.startswith("["):
        closing = parts.netloc.find("]")
        suffix = parts.netloc[closing + 1:]
        if suffix and not re.fullmatch(r":[0-9]+", suffix):
            raise ValueError("The IPv6 address or its port is invalid.")
        try:
            if "%" in hostname:
                raise ValueError("IPv6 scope identifiers are not supported.")
            ipaddress.IPv6Address(hostname)
        except ValueError as exc:
            raise ValueError("Enter a valid IPv6 address enclosed in square brackets.") from exc
    elif ":" in hostname or "[" in parts.netloc or "]" in parts.netloc:
        raise ValueError("IPv6 addresses must be enclosed in square brackets.")
    else:
        _validate_hostname(hostname)
    return normalized


def _validate_hostname(hostname: str) -> None:
    try:
        ascii_host = hostname.encode("idna").decode("ascii").removesuffix(".")
    except UnicodeError as exc:
        raise ValueError("The website host name is invalid.") from exc
    if not ascii_host or len(ascii_host) > 253:
        raise ValueError("The website host name is invalid.")
    if any(not _DNS_LABEL.fullmatch(label) for label in ascii_host.split(".")):
        raise ValueError("The website host name is invalid.")
    if re.fullmatch(r"[0-9.]+", ascii_host):
        try:
            ipaddress.IPv4Address(ascii_host)
        except ValueError as exc:
            raise ValueError("Enter a valid IPv4 address.") from exc
