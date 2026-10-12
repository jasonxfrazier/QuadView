"""Physical-pixel window geometry and conservative native window identities."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import threading
import time

import pywintypes
import win32api
import win32con
import win32gui
import win32process

from .browser_manager import normalized_path, read_process_identity
from .models import Monitor, Rect, WindowSnapshot


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
_PM_V2 = ctypes.c_void_p(-4)
_FENCE_MESSAGE = win32con.WM_APP + 17
_EVENT_CREATE, _EVENT_DESTROY, _EVENT_SHOW = 0x8000, 0x8001, 0x8002
_WinEventProc = ctypes.WINFUNCTYPE(
    None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
)

_user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
_user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
_user32.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
_user32.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
_user32.GetThreadDpiAwarenessContext.argtypes = []
_user32.GetThreadDpiAwarenessContext.restype = wintypes.HANDLE
_user32.AreDpiAwarenessContextsEqual.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_user32.AreDpiAwarenessContextsEqual.restype = wintypes.BOOL
_user32.SetWinEventHook.argtypes = [
    wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, _WinEventProc,
    wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
]
_user32.SetWinEventHook.restype = wintypes.HANDLE
_user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
_user32.UnhookWinEvent.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = ctypes.c_int
_user32.PeekMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT,
]
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.restype = wintypes.LPARAM
_user32.ShowWindowAsync.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.ShowWindowAsync.restype = wintypes.BOOL
_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD
_dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


def _ensure_thread_dpi() -> None:
    if not _user32.SetThreadDpiAwarenessContext(_PM_V2):
        raise ctypes.WinError(ctypes.get_last_error())
    if not _user32.AreDpiAwarenessContextsEqual(_user32.GetThreadDpiAwarenessContext(), _PM_V2):
        raise RuntimeError("Windows could not enable per-monitor DPI awareness for window management.")


def configure_dpi_awareness() -> None:
    """Call before QApplication or any native window is created (Windows 10+)."""
    if not _user32.SetProcessDpiAwarenessContext(_PM_V2):
        error = ctypes.get_last_error()
        if error != 5:  # Already established by a manifest, Qt, or the host process.
            raise ctypes.WinError(error)
    _ensure_thread_dpi()


class WindowManager:
    """Track window lifetimes without using captions or reading page content.

    WinEvent notifications are asynchronous. Fences drain the observer's message
    loop before snapshots and mutations, and identities include both process
    creation time and a handle generation. Native HWND checks cannot make a
    cross-process operation atomic; ambiguity is always handled conservatively.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fence_lock = threading.Lock()
        self._ready = threading.Event()
        self._fence = threading.Event()
        self._fence_serial = 0
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._error: Exception | None = None
        self._generations: dict[int, int] = {}
        self._next_generation = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._check_observer()
            return
        self._ready.clear()
        self._error = None
        with self._lock:
            self._generations.clear()
        self._thread = threading.Thread(target=self._observe, name="QuadView-WinEvents", daemon=True)
        self._thread.start()
        if not self._ready.wait(3):
            raise RuntimeError("Windows window-event observation did not start in time.")
        self._check_observer()

    def stop(self) -> None:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        if not _user32.PostThreadMessageW(self._thread_id, win32con.WM_QUIT, 0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        thread.join(timeout=3)
        if thread.is_alive():
            raise RuntimeError("Windows window-event observation did not stop in time.")
        with self._lock:
            self._generations.clear()

    def _check_observer(self) -> None:
        if self._error is not None:
            raise RuntimeError("Windows window-event observation failed.") from self._error
        if self._thread is None or not self._thread.is_alive():
            raise RuntimeError("Window observation must be running before managing browser windows.")

    def _observe(self) -> None:
        hook = None
        callback = _WinEventProc(self._on_event)  # Keep callback alive until unhooked.
        try:
            _ensure_thread_dpi()
            self._thread_id = _kernel32.GetCurrentThreadId()
            message = wintypes.MSG()
            _user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)  # Create thread message queue.
            hook = _user32.SetWinEventHook(_EVENT_CREATE, _EVENT_SHOW, None, callback, 0, 0, 2)
            if not hook:
                raise ctypes.WinError(ctypes.get_last_error())
            self._ready.set()
            while True:
                result = _user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    raise ctypes.WinError(ctypes.get_last_error())
                if result == 0:
                    break
                if message.message == _FENCE_MESSAGE:
                    if message.wParam == self._fence_serial:
                        self._fence.set()
                else:
                    _user32.TranslateMessage(ctypes.byref(message))
                    _user32.DispatchMessageW(ctypes.byref(message))
        except (OSError, RuntimeError) as error:
            self._error = error
        finally:
            if hook:
                _user32.UnhookWinEvent(hook)
            self._ready.set()

    def _on_event(
        self, hook: int, event: int, hwnd: int, object_id: int,
        child_id: int, event_thread: int, event_time: int,
    ) -> None:
        if not hwnd or object_id != 0 or child_id != 0:
            return
        with self._lock:
            if event == _EVENT_DESTROY:
                self._generations.pop(hwnd, None)
            elif hwnd not in self._generations:
                # Accessibility providers can repeat CREATE for an existing
                # window. Its lifetime changes only after an observed destroy.
                self._next_generation += 1
                self._generations[hwnd] = self._next_generation

    def _flush_events(self) -> None:
        self._check_observer()
        with self._fence_lock:
            self._fence_serial += 1
            self._fence.clear()
            if not _user32.PostThreadMessageW(self._thread_id, _FENCE_MESSAGE, self._fence_serial, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            if not self._fence.wait(2):
                raise RuntimeError("Windows window-event observation is not responding.")
        self._check_observer()

    def monitors(self) -> list[Monitor]:
        _ensure_thread_dpi()
        monitors: list[Monitor] = []
        for handle, _dc, _rect in win32api.EnumDisplayMonitors():
            information = win32api.GetMonitorInfo(handle)
            device = information["Device"]
            identifier, name = device, device
            try:
                display = win32api.EnumDisplayDevices(device, 0, 1)
                identifier = display.DeviceID or device
                name = display.DeviceString or device
            except pywintypes.error:
                # Remote and virtual displays may expose only a GDI device name.
                pass
            monitors.append(Monitor(
                identifier=identifier,
                name=f"{name} ({device})",
                work_area=Rect(*information["Work"]),
                bounds=Rect(*information["Monitor"]),
                is_primary=bool(information["Flags"] & 1),
            ))
        return sorted(monitors, key=lambda monitor: (not monitor.is_primary, monitor.bounds.left, monitor.bounds.top))

    def enumerate_windows(self, executable: str) -> list[WindowSnapshot]:
        _ensure_thread_dpi()
        self._flush_events()
        expected_image = normalized_path(executable)
        windows: list[WindowSnapshot] = []

        def collect(hwnd: int, _context: object) -> bool:
            try:
                if (not win32gui.IsWindowVisible(hwnd)
                        or win32gui.GetClassName(hwnd) != "MozillaWindowClass"
                        or win32gui.GetWindow(hwnd, win32con.GW_OWNER)):
                    return True
                cloaked = wintypes.DWORD()
                if (_dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0
                        and cloaked.value):
                    return True
                _thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = read_process_identity(pid)
                if process.created_at == 0 or process.image_path != expected_image:
                    return True
                with self._lock:
                    if hwnd not in self._generations:
                        self._next_generation += 1
                        self._generations[hwnd] = self._next_generation
                    generation = self._generations[hwnd]
                windows.append(WindowSnapshot(hwnd=hwnd, process=process, generation=generation))
            except (OSError, pywintypes.error):
                # Windows can disappear between enumeration and identity lookup.
                return True
            return True

        win32gui.EnumWindows(collect, None)
        self._flush_events()
        # An event processed during enumeration can invalidate its first result.
        with self._lock:
            return [window for window in windows if self._generations.get(window.hwnd) == window.generation]

    def identity_alive(self, window: WindowSnapshot) -> bool:
        _ensure_thread_dpi()
        self._flush_events()
        if not window.process.created_at:
            return False
        with self._lock:
            if self._generations.get(window.hwnd) != window.generation:
                return False
        try:
            if (not win32gui.IsWindow(window.hwnd)
                    or win32gui.GetClassName(window.hwnd) != "MozillaWindowClass"
                    or win32gui.GetWindow(window.hwnd, win32con.GW_OWNER)):
                return False
            _thread_id, pid = win32process.GetWindowThreadProcessId(window.hwnd)
            if pid != window.process.pid or read_process_identity(pid) != window.process:
                return False
        except (OSError, pywintypes.error):
            return False
        with self._lock:
            return self._generations.get(window.hwnd) == window.generation

    def _require_identity(self, window: WindowSnapshot) -> None:
        if not self.identity_alive(window):
            raise RuntimeError("A managed LibreWolf window closed or its identity changed. It was left untouched.")

    def bounds(self, window: WindowSnapshot) -> Rect:
        self._require_identity(window)
        frame = wintypes.RECT()
        result = _dwmapi.DwmGetWindowAttribute(window.hwnd, 9, ctypes.byref(frame), ctypes.sizeof(frame))
        if result != 0:
            raise RuntimeError("Windows could not read the visible LibreWolf window frame.")
        return Rect(frame.left, frame.top, frame.right, frame.bottom)

    def place(self, window: WindowSnapshot, rect: Rect) -> Rect:
        if rect.width <= 0 or rect.height <= 0:
            raise ValueError("A browser quadrant must have positive width and height.")
        self._require_identity(window)
        if win32gui.IsIconic(window.hwnd) or win32gui.GetWindowPlacement(window.hwnd)[1] == win32con.SW_SHOWMAXIMIZED:
            if not _user32.ShowWindowAsync(window.hwnd, win32con.SW_SHOWNOACTIVATE):
                raise RuntimeError("Windows could not restore the managed LibreWolf window.")
            restore_deadline = time.monotonic() + 2
            while win32gui.IsIconic(window.hwnd) or win32gui.GetWindowPlacement(window.hwnd)[1] == win32con.SW_SHOWMAXIMIZED:
                self._require_identity(window)
                if time.monotonic() >= restore_deadline:
                    raise RuntimeError("LibreWolf did not restore its window in time. Restore it and reapply the layout.")
                time.sleep(0.05)

        actual = self.bounds(window)
        for _attempt in range(3):
            outer = Rect(*win32gui.GetWindowRect(window.hwnd))
            requested = Rect(
                rect.left + outer.left - actual.left,
                rect.top + outer.top - actual.top,
                rect.right + outer.right - actual.right,
                rect.bottom + outer.bottom - actual.bottom,
            )
            self._require_identity(window)
            win32gui.SetWindowPos(
                window.hwnd, 0, requested.left, requested.top, requested.width, requested.height,
                win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER | win32con.SWP_NOOWNERZORDER | 0x4000,
            )
            deadline = time.monotonic() + 0.6
            while time.monotonic() < deadline:
                time.sleep(0.05)
                actual = self.bounds(window)
                if actual == rect:
                    return actual
        raise RuntimeError(
            "LibreWolf could not fit the requested quadrant "
            f"({rect.width} × {rect.height} pixels; actual {actual.width} × {actual.height}). "
            "Its minimum window size or fullscreen state may prevent this layout."
        )

    def close(self, window: WindowSnapshot) -> None:
        self._require_identity(window)
        win32gui.PostMessage(window.hwnd, win32con.WM_CLOSE, 0, 0)

