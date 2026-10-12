"""Local application settings; browser profiles are never read or changed."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from .models import AppConfig, DEFAULT_SOURCE_URL, Rect


def default_config_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "QuadView" / "config.json"


class ConfigManager:
    """Read versioned settings and replace them atomically on save.

    Invalid or unsupported files stay untouched during loading. Before a later
    save replaces one, its exact bytes are preserved in a uniquely named backup.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()
        self.last_warning: str | None = None
        self._preserve_on_save = False
        self._loaded = False

    def load(self) -> AppConfig:
        self.last_warning = None
        self._preserve_on_save = False
        self._loaded = True
        try:
            contents = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return AppConfig()
        except (OSError, UnicodeError):
            self._preserve_on_save = True
            self.last_warning = (
                "Saved settings could not be read. Defaults were loaded; "
                "the existing file will be preserved before settings are saved."
            )
            return AppConfig()

        try:
            return _parse_config(json.loads(contents))
        except (ValueError, TypeError, KeyError, RecursionError):
            self._preserve_on_save = True
            self.last_warning = (
                "Saved settings are invalid or use an unsupported version. "
                "Defaults were loaded; the existing file will be preserved "
                "before settings are saved."
            )
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        """Save validated settings, raising OSError if durable storage fails."""
        document = asdict(config)
        _parse_config(document)
        encoded = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if not self._loaded:
            self.load()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        backup_path: Path | None = None
        if self._preserve_on_save and self.path.exists():
            # Read first so that inability to preserve the original fails safely.
            original = self.path.read_bytes()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = self.path.with_name(
                f"{self.path.stem}.{timestamp}.{uuid4().hex[:8]}.backup{self.path.suffix}"
            )
            with backup_path.open("xb") as backup:
                backup.write(original)
                backup.flush()
                os.fsync(backup.fileno())

        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=f".{self.path.name}.", suffix=".tmp",
                dir=self.path.parent, delete=False,
            ) as output:
                temporary = Path(output.name)
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self._preserve_on_save = False
        if backup_path is not None:
            self.last_warning = f"Previous settings were preserved in {backup_path.name}."


def _parse_config(document: Any) -> AppConfig:
    if not isinstance(document, dict):
        raise ValueError("Settings must be a JSON object.")
    if type(document.get("version")) is not int or document["version"] != 1:
        raise ValueError("Unsupported settings version.")
    urls = document.get("urls", [])
    if not isinstance(urls, list) or len(urls) > 4 or any(not isinstance(url, str) for url in urls):
        raise ValueError("Settings may contain up to four selected URL strings.")
    source_url = document.get("source_url", DEFAULT_SOURCE_URL)
    executable_path = document.get("executable_path", "")
    monitor_id = document.get("monitor_id", "")
    if any(not isinstance(value, str) for value in (source_url, executable_path, monitor_id)):
        raise ValueError("Source URL, executable path, and monitor ID must be strings.")
    return AppConfig(
        version=1,
        urls=urls.copy(),
        source_url=source_url or DEFAULT_SOURCE_URL,
        executable_path=executable_path,
        monitor_id=monitor_id,
        monitor_bounds=_parse_rect(document.get("monitor_bounds")),
        window_geometry=_parse_rect(document.get("window_geometry")),
    )


def _parse_rect(value: Any) -> Rect | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Geometry must be a JSON object.")
    coordinates = [value[key] for key in ("left", "top", "right", "bottom")]
    if any(type(coordinate) is not int for coordinate in coordinates):
        raise ValueError("Geometry coordinates must be integers.")
    rect = Rect(*coordinates)
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError("Geometry dimensions must be positive.")
    return rect
