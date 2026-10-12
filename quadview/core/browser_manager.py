"""Use the installed LibreWolf without changing its profile or preferences."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
import winreg

import pywintypes
import win32api

from .models import ProcessIdentity


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


_kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
_kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
_kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
_kernel32.Process32FirstW.restype = wintypes.BOOL
_kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry)]
_kernel32.Process32NextW.restype = wintypes.BOOL
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL
_kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
_kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
]
_kernel32.GetProcessTimes.restype = wintypes.BOOL


def normalized_path(path: str) -> str:
    """Compare queried Windows paths without relying on letter casing."""
    return os.path.normcase(os.path.realpath(path))


def read_process_identity(pid: int) -> ProcessIdentity:
    """Read image and raw creation FILETIME through one process handle.

    A process may exit during discovery; callers decide whether that is an
    ordinary disappearing candidate or an error affecting an active session.
    """
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        image = ctypes.create_unicode_buffer(32768)
        length = wintypes.DWORD(len(image))
        if not _kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        creation, end, kernel, user = (wintypes.FILETIME() for _ in range(4))
        if not _kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(end),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        created_at = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return ProcessIdentity(pid=pid, created_at=created_at, image_path=normalized_path(image.value))
    finally:
        _kernel32.CloseHandle(handle)


class BrowserManager:
    """Locate, inspect, and launch the user's existing browser installation."""

    def detect_executable(self, saved: str = "") -> str | None:
        candidates = [saved] if saved else []
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(
                        root,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\librewolf.exe",
                        0, winreg.KEY_READ | view,
                    ) as key:
                        value, kind = winreg.QueryValueEx(key, None)
                        if kind in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                            candidates.append(os.path.expandvars(value.strip('"')))
                except FileNotFoundError:
                    continue
                except PermissionError:
                    # A locked registry location must not defeat the manual picker.
                    continue
        for variable in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
            if directory := os.environ.get(variable):
                candidates.append(str(Path(directory) / "LibreWolf" / "librewolf.exe"))
        if directory := os.environ.get("LOCALAPPDATA"):
            candidates.extend([
                str(Path(directory) / "Programs" / "LibreWolf" / "librewolf.exe"),
                str(Path(directory) / "LibreWolf" / "librewolf.exe"),
            ])
        if found := shutil.which("librewolf.exe"):
            candidates.append(found)
        for candidate in dict.fromkeys(candidates):
            try:
                return self.validate_executable(candidate)
            except (ValueError, OSError):
                continue
        return None

    def validate_executable(self, path: str) -> str:
        candidate = Path(os.path.expandvars(path)).expanduser()
        if candidate.name.casefold() != "librewolf.exe" or not candidate.is_file():
            raise ValueError("Select an existing librewolf.exe from your LibreWolf installation.")
        candidate = candidate.resolve()
        try:
            translations = win32api.GetFileVersionInfo(str(candidate), r"\VarFileInfo\Translation")
            products = [
                win32api.GetFileVersionInfo(
                    str(candidate), rf"\StringFileInfo\{language:04x}{codepage:04x}\ProductName"
                )
                for language, codepage in translations
            ]
        except pywintypes.error as error:
            raise ValueError("The selected executable does not identify itself as LibreWolf.") from error
        if not any(product.strip().casefold() == "librewolf" for product in products):
            raise ValueError("The selected executable does not identify itself as LibreWolf.")
        return str(candidate)

    def running_processes(self) -> list[ProcessIdentity]:
        """Include inaccessible LibreWolf processes so launch fails conservatively."""
        snapshot = _kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
        if snapshot == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        found: list[ProcessIdentity] = []
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        try:
            valid = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while valid:
                if entry.szExeFile.casefold() == "librewolf.exe":
                    try:
                        found.append(read_process_identity(entry.th32ProcessID))
                    except OSError:
                        # It may have exited, or access may be denied. Either way
                        # a conservative refusal is safer than assuming no browser.
                        found.append(ProcessIdentity(
                            pid=entry.th32ProcessID, created_at=0, image_path="librewolf.exe"
                        ))
                valid = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            error = ctypes.get_last_error()
            if error != 18:  # ERROR_NO_MORE_FILES
                raise ctypes.WinError(error)
        finally:
            _kernel32.CloseHandle(snapshot)
        return found

    def launch(self, executable: str, url: str) -> None:
        # Do not use --no-remote, --new-instance, --profile or --private-window:
        # normal LibreWolf startup selects the existing installation profile.
        subprocess.Popen(
            [self.validate_executable(executable), "--new-window", url],
            shell=False,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
