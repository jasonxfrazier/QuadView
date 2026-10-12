"""Serialize native operations on a Qt worker thread."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from ..core.models import AppConfig
from ..core.session_manager import SessionManager

logger = logging.getLogger(__name__)


class SessionWorker(QObject):
    """Create adapters lazily, after this object has moved to its QThread.

    Only cancel() is called directly from the UI thread. It sets thread-safe
    events; all adapter work, including shutdown, goes through perform().
    A factory permits fake adapters in tests without starting a browser.
    """

    update = Signal(object)
    completed = Signal(str, object, str)
    finished = Signal()

    def __init__(
        self,
        factory: Callable[[Callable[[Any], None]], SessionManager] | None = None,
    ) -> None:
        super().__init__()
        self._factory = factory
        self._session: SessionManager | None = None
        self._stopping = threading.Event()
        self._session_lock = threading.Lock()

    def _manager(self) -> SessionManager:
        with self._session_lock:
            if self._session is None:
                if self._factory is not None:
                    self._session = self._factory(self.update.emit)
                else:
                    from ..core.browser_manager import BrowserManager
                    from ..core.window_manager import WindowManager

                    self._session = SessionManager(
                        BrowserManager(), WindowManager(), on_update=self.update.emit
                    )
            return self._session

    def cancel(self) -> None:
        """Stop accepting operations and request cancellation of an active one."""
        self._stopping.set()
        with self._session_lock:
            session = self._session
        if session is not None:
            session.cancel()

    @Slot(str, object)
    def perform(self, command: str, payload: object = None) -> None:
        if self._stopping.is_set() and command != "shutdown":
            self.completed.emit(command, None, "Operation cancelled. Browser windows remain open.")
            return
        result: object = None
        error = ""
        try:
            session = self._manager()
            if command == "inspect":
                if not isinstance(payload, AppConfig):
                    raise ValueError("The saved application settings could not be inspected.")
                executable = session.browser.detect_executable(payload.executable_path)  # type: ignore[attr-defined]
                result = {
                    "monitors": session.windows.monitors(),
                    "executable": executable or "",
                    "requested_executable": payload.executable_path,
                    "running": bool(session.browser.running_processes()),
                }
            elif command == "launch":
                if not isinstance(payload, AppConfig):
                    raise ValueError("The launch settings are invalid.")
                session.launch(payload)
            elif command == "fetch":
                from ..core.link_discovery import extract_good_links, get_links
                if not isinstance(payload, str):
                    raise ValueError("Enter a source page address.")
                result = extract_good_links(get_links(payload, cancelled=self._stopping))
            elif command == "reapply":
                session.reapply(str(payload) if payload is not None else None)
            elif command == "close":
                session.close()
            elif command == "refresh":
                session.refresh()
                result = {
                    "running": bool(session.browser.running_processes()),
                    "managed_count": len(session.managed),
                    "state": session.state,
                }
            elif command == "shutdown":
                session.shutdown()
            else:
                raise ValueError("The requested application operation is unavailable.")
        except (RuntimeError, ValueError) as exc:
            error = str(exc)
        except OSError:
            error = "Windows could not complete this operation. Check LibreWolf and try again."
        except Exception as exc:
            # Avoid traceback/local-variable logging that could include URLs.
            logger.error("worker_operation_failed", extra={"command": command, "error_type": type(exc).__name__})
            error = "The operation could not be completed. Please retry or restart QuadView."
        self.completed.emit(command, result, error)
        if command == "shutdown":
            if error:
                self._stopping.clear()
            else:
                self.finished.emit()
