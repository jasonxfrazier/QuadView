"""User-requested link extraction in a disposable Playwright Chromium browser."""

from __future__ import annotations

from threading import Event
from urllib.parse import urlsplit

from playwright.sync_api import Error, Page, TimeoutError as PlaywrightTimeout, sync_playwright

from .url_validation import normalize_url


class LinkFetchError(RuntimeError):
    """Safe actionable error without the page URL or Playwright call log."""


def extract_links(page: Page) -> list[str]:
    return page.locator("a[href], area[href]").evaluate_all("""
        elements => [...new Set(elements
            .filter(element => element.checkVisibility({
                checkOpacity: true, checkVisibilityCSS: true
            }))
            .map(element => element.href)
            .filter(url => /^https?:/.test(url)))]
    """)


def get_links(url: str, *, cancelled: Event | None = None) -> list[str]:
    """Wait for load just as in the supplied script; always close the scraper.

    The caller runs this on a worker thread. Cancellation is honored before
    launch and after navigation; an in-flight navigation has a 60-second limit.
    The app never installs a browser automatically.
    """
    normalized = normalize_url(url)
    if cancelled is not None and cancelled.is_set():
        raise LinkFetchError("Link discovery was cancelled.")
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=False, timeout=15_000)
            except Error as error:
                raise LinkFetchError(
                    "Chromium could not start for link discovery. "
                    "Install it with: uv run playwright install chromium"
                ) from error
            try:
                page = browser.new_page()
                page.goto(normalized, wait_until="load", timeout=60_000)
                if cancelled is not None and cancelled.is_set():
                    raise LinkFetchError("Link discovery was cancelled.")
                return extract_links(page)
            finally:
                browser.close()
    except PlaywrightTimeout as error:
        raise LinkFetchError("The source page did not finish loading within 60 seconds. Try fetching it again.") from error
    except Error as error:
        raise LinkFetchError("Could not fetch links. Check the source address and whether its page loads normally.") from error


def is_stream_link(url: str) -> bool:
    """Match the literal /stream/ segment in the URL path, not query or fragment."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme.lower() in {"http", "https"} and bool(parts.netloc) and "/stream/" in parts.path


def extract_good_links(links: list[str]) -> dict[str, str]:
    """Use the requested /stream/ path filter and original literal name splitting.

    Matching names overwrite their URL, as in the user's original dictionary.
    Query strings, fragments and trailing slashes are not rewritten.
    """
    res = {}
    for link in links:
        if not is_stream_link(link):
            continue
        name = ' '.join(link.split('/')[-1].split('-')).title()
        res[name] = link
    return res
