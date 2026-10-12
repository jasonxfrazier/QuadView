"""Serialized session operations; all methods run outside the GUI thread.

Window discovery is deliberately conservative. Native windows do not expose a
URL identity contract: the association relies on one stable candidate following
each sequential request. Ambiguous sets are rejected; automatic association
assumes no concurrent browser-window creation during startup.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Protocol

from .layout_manager import regions_for_count
from .models import (
    AppConfig, ManagedWindow, Monitor, ProcessIdentity, Rect, SessionState,
    SessionUpdate, WindowSnapshot,
)
from .url_validation import normalize_url

logger = logging.getLogger(__name__)

RUNNING_MESSAGE = (
    "LibreWolf must be completely closed before launching QuadView. "
    "Please close all LibreWolf windows and try again."
)


class SessionError(RuntimeError):
    """An actionable session failure, safe to display without browsing data."""


class BrowserAdapter(Protocol):
    def validate_executable(self, path: str) -> str: ...
    def running_processes(self) -> list[ProcessIdentity]: ...
    def launch(self, executable: str, url: str) -> None: ...


class WindowAdapter(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def monitors(self) -> list[Monitor]: ...
    def enumerate_windows(self, executable: str) -> list[WindowSnapshot]: ...
    def identity_alive(self, window: WindowSnapshot) -> bool: ...
    def place(self, window: WindowSnapshot, rect: Rect) -> Rect: ...
    def bounds(self, window: WindowSnapshot) -> Rect: ...
    def close(self, window: WindowSnapshot) -> None: ...


class SessionManager:
    def __init__(
        self,
        browser: BrowserAdapter,
        windows: WindowAdapter,
        on_update: Callable[[SessionUpdate], None] | None = None,
        *,
        launch_timeout: float = 35.0,
        close_timeout: float = 15.0,
        settle_time: float = 1.5,
        poll_interval: float = 0.1,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        wall_time_ns: Callable[[], int] = time.time_ns,
    ) -> None:
        self.browser = browser
        self.windows = windows
        self.state = SessionState.IDLE
        self.managed: list[ManagedWindow] = []
        self.monitor_id = ""
        self.executable = ""
        self._notify = on_update or (lambda update: None)
        self._launch_timeout = launch_timeout
        self._close_timeout = close_timeout
        self._settle_time = settle_time
        self._poll_interval = poll_interval
        self._clock = monotonic
        self._sleep = sleep
        self._wall_time_ns = wall_time_ns
        self._launch_boundary = 0
        self._browser_process: ProcessIdentity | None = None
        self._operation = threading.Lock()
        self._cancel = threading.Event()
        self._started = False

    def _update(self, state: SessionState, message: str) -> None:
        self.state = state
        logger.info("session_state", extra={"state": state.value, "count": len(self.managed)})
        self._notify(SessionUpdate(state, message, len(self.managed)))

    def cancel(self) -> None:
        """Thread-safe cancellation, never a process termination request."""
        self._cancel.set()

    def _check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise SessionError("Operation cancelled. Any managed windows remain open.")

    def _begin(self) -> None:
        if not self._operation.acquire(blocking=False):
            raise SessionError("Another session operation is still in progress.")
        self._cancel.clear()

    def _ensure_started(self) -> None:
        if not self._started:
            self.windows.start()
            self._started = True

    def _prune(self) -> None:
        self.managed = [item for item in self.managed if self.windows.identity_alive(item.window)]

    def _monitor(self) -> Monitor:
        for monitor in self.windows.monitors():
            if monitor.identifier == self.monitor_id:
                return monitor
        raise SessionError("The selected monitor is no longer available. Select a connected monitor.")

    def _discover(
        self, baseline: set[WindowSnapshot], expected: set[WindowSnapshot]
    ) -> WindowSnapshot:
        deadline = self._clock() + self._launch_timeout
        candidate: WindowSnapshot | None = None
        stable_since = self._clock()
        while self._clock() < deadline:
            self._check_cancelled()
            self._monitor()  # A disconnected monitor must not silently change the destination.
            current = set(self.windows.enumerate_windows(self.executable))
            if not expected.issubset(current):
                raise SessionError("A managed window closed during startup. Close the partial session and retry.")
            new_windows = current - baseline
            if len(new_windows) > 1:
                raise SessionError(
                    "More than one LibreWolf window appeared for a launch request. "
                    "Restored or manually opened windows cannot be assigned safely. "
                    "Unassigned windows have been left untouched."
                )
            if new_windows:
                found = next(iter(new_windows))
                if found.process.created_at < self._launch_boundary:
                    raise SessionError("A browser process predates this launch. Its window was left untouched.")
                if self._browser_process is not None and found.process != self._browser_process:
                    raise SessionError("A different LibreWolf process created a window during startup. It was left untouched.")
                if candidate != found:
                    candidate, stable_since = found, self._clock()
                elif self._clock() - stable_since >= self._settle_time:
                    if self.windows.identity_alive(found):
                        return found
            else:
                candidate = None
                stable_since = self._clock()
            self._sleep(self._poll_interval)
        raise SessionError(
            "LibreWolf did not create an identifiable window in time. "
            "Check for a profile chooser, browser startup dialog, or background process. "
            "Any unassigned windows have been left untouched."
        )

    def launch(self, config: AppConfig) -> None:
        self._begin()
        try:
            self._prune()
            if self.managed:
                raise SessionError("Close the current QuadView session before launching another.")
            self._update(SessionState.VALIDATING, "Checking LibreWolf, websites, and monitor…")
            if not 1 <= len(config.urls) <= 4:
                raise SessionError("Select between one and four links.")
            urls = [normalize_url(value) for value in config.urls]
            if len(set(urls)) != len(urls):
                raise SessionError("Select each link only once.")
            self.executable = self.browser.validate_executable(config.executable_path)
            if self.browser.running_processes():
                raise SessionError(RUNNING_MESSAGE)
            self.monitor_id = config.monitor_id
            self._monitor()
            self._ensure_started()
            baseline = set(self.windows.enumerate_windows(self.executable))
            if baseline or self.browser.running_processes():
                raise SessionError(RUNNING_MESSAGE)
            self._browser_process = None
            # Windows process creation times use 100 ns ticks since 1601.
            self._launch_boundary = self._wall_time_ns() // 100 + 116444736000000000
            for quadrant, url in enumerate(urls):
                self._check_cancelled()
                expected = {item.window for item in self.managed}
                current = set(self.windows.enumerate_windows(self.executable))
                if current != baseline:
                    raise SessionError("LibreWolf windows changed during startup. Unassigned windows remain untouched.")
                self._update(SessionState.LAUNCHING, f"Launching window {quadrant + 1} of {len(urls)}…")
                self.browser.launch(self.executable, url)
                window = self._discover(baseline, expected)
                if self._browser_process is None:
                    self._browser_process = window.process
                self.managed.append(ManagedWindow(quadrant, window))
                baseline.add(window)
                # Retain original selection order when survivors later reflow.
                self.windows.place(window, regions_for_count(self._monitor().work_area, len(urls))[quadrant])
            if set(self.windows.enumerate_windows(self.executable)) != baseline:
                raise SessionError("Additional LibreWolf windows appeared during startup and remain unmanaged.")
            self._update(SessionState.ACTIVE, f"Session active ? {len(self.managed)} windows")
        except Exception as exc:
            self._prune_after_failure()
            self._update(SessionState.ERROR, str(exc))
            raise
        finally:
            self._operation.release()

    def _prune_after_failure(self) -> None:
        try:
            self._prune()
        except Exception:
            # Retain identities when inspection itself fails. Never guess ownership.
            logger.warning("window_reconciliation_failed")

    def reapply(self, monitor_id: str | None = None) -> None:
        self._begin()
        try:
            self._prune()
            if not self.managed:
                raise SessionError("There are no managed windows to arrange.")
            if monitor_id is not None:
                self.monitor_id = monitor_id
            regions = regions_for_count(self._monitor().work_area, len(self.managed))
            for item, region in zip(self.managed, regions):
                self._check_cancelled()
                self.windows.place(item.window, region)
            self._update(SessionState.ACTIVE, f"Layout restored · {len(self.managed)} windows")
        except Exception as exc:
            self._update(SessionState.ERROR, str(exc))
            raise
        finally:
            self._operation.release()

    def close(self) -> None:
        self._begin()
        try:
            self._prune()
            if not self.managed:
                self._update(SessionState.IDLE, "No managed browser windows remain open.")
                return
            self._update(SessionState.CLOSING, "Waiting for LibreWolf windows to close…")
            # Request each closure once. Browser prompts must be handled by the user.
            for item in list(self.managed):
                if self.windows.identity_alive(item.window):
                    self.windows.close(item.window)
            deadline = self._clock() + self._close_timeout
            while self.managed and self._clock() < deadline:
                self._check_cancelled()
                self._prune()
                if self.managed:
                    self._sleep(self._poll_interval)
            if self.managed:
                raise SessionError(
                    "LibreWolf is waiting to close. Check its confirmation dialogs, "
                    "then try Close QuadView Session again. No processes were terminated."
                )
            self._update(SessionState.IDLE, "Session closed. LibreWolf may take a moment to finish shutting down.")
        except Exception as exc:
            self._update(SessionState.ERROR, str(exc))
            raise
        finally:
            self._operation.release()

    def refresh(self) -> None:
        """Reconcile manual closures between operations without adopting windows."""
        if not self._operation.acquire(blocking=False):
            return
        try:
            previous = len(self.managed)
            self._prune()
            if previous and not self.managed:
                self._update(SessionState.IDLE, "All managed windows have closed.")
            elif previous != len(self.managed):
                if self.state == SessionState.ACTIVE:
                    regions = regions_for_count(self._monitor().work_area, len(self.managed))
                    for item, region in zip(self.managed, regions):
                        self.windows.place(item.window, region)
                self._update(self.state, f"{len(self.managed)} managed windows remain open.")
        finally:
            self._operation.release()

    def shutdown(self) -> None:
        """Release observer resources; never close browser windows on app exit."""
        if not self._operation.acquire(blocking=False):
            raise SessionError("Wait for the current operation to finish before stopping window observation.")
        try:
            if self._started:
                self.windows.stop()
                self._started = False
        finally:
            self._operation.release()
