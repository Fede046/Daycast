"""Le poche chiamate Win32 che servono al logger, via ctypes (niente pywin32)."""

from __future__ import annotations

import ctypes
import os
import re
from ctypes import wintypes
from functools import lru_cache

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
powrprof = ctypes.WinDLL("powrprof")
version = ctypes.WinDLL("version")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ALREADY_EXISTS = 183
SYSTEM_EXECUTION_STATE = 16
ES_DISPLAY_REQUIRED = 0x2


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.EnumChildWindows.argtypes = [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.GetTickCount.restype = wintypes.DWORD
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID]
version.VerQueryValueW.argtypes = [wintypes.LPCVOID, wintypes.LPCWSTR, ctypes.POINTER(wintypes.LPVOID), ctypes.POINTER(wintypes.UINT)]


def foreground_window() -> int | None:
    return user32.GetForegroundWindow() or None


def window_title(hwnd: int) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_path(pid: int) -> str | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def uwp_child_pid(hwnd: int, host_pid: int) -> int | None:
    """Le app dello Store girano dentro ApplicationFrameHost: il processo vero è una finestra figlia."""
    found: list[int] = []

    def visit(child, _lparam):
        pid = window_pid(child)
        if pid != host_pid:
            found.append(pid)
            return False
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(visit), 0)
    return found[0] if found else None


@lru_cache(maxsize=256)
def app_display_name(path: str) -> str:
    """Il nome leggibile dell'eseguibile (es. Code.exe -> "Visual Studio Code")."""
    return _TECH_SUFFIX.sub("", _raw_display_name(path)) or os.path.basename(path)


# suffissi tecnici che alcune app dello Store mettono nel nome: "WhatsApp.Root" -> "WhatsApp"
_TECH_SUFFIX = re.compile(r"\.(Root|App|exe)$", re.IGNORECASE)


def _raw_display_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return stem
    data = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, data):
        return stem

    ptr = wintypes.LPVOID()
    length = wintypes.UINT()
    langs = []
    if version.VerQueryValueW(data, "\\VarFileInfo\\Translation", ctypes.byref(ptr), ctypes.byref(length)) and length.value:
        pairs = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD * 2))
        for i in range(length.value // 4):
            lang, cp = pairs[i]
            langs.append(f"{lang:04x}{cp:04x}")
    langs += ["040904b0", "040904e4", "041004b0"]

    for key in ("FileDescription", "ProductName"):
        for lang in langs:
            if version.VerQueryValueW(data, f"\\StringFileInfo\\{lang}\\{key}", ctypes.byref(ptr), ctypes.byref(length)) and length.value:
                text = ctypes.wstring_at(ptr, length.value).rstrip("\x00").strip()
                if text:
                    return text
    return stem


def idle_seconds() -> float:
    info = LASTINPUTINFO(cbSize=ctypes.sizeof(LASTINPUTINFO))
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    # entrambi i contatori sono a 32 bit e ripartono da zero ogni ~49 giorni
    return ((kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000


def display_required() -> bool:
    """True se qualche programma tiene acceso lo schermo (video in riproduzione, giochi...)."""
    state = wintypes.ULONG()
    status = powrprof.CallNtPowerInformation(
        SYSTEM_EXECUTION_STATE, None, 0, ctypes.byref(state), ctypes.sizeof(state)
    )
    return status == 0 and bool(state.value & ES_DISPLAY_REQUIRED)


def single_instance(name: str):
    """Restituisce un handle se siamo l'unica istanza, altrimenti None."""
    handle = kernel32.CreateMutexW(None, False, name)
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle
