"""Comandi al logger in esecuzione (pausa, ripresa, stato) dall'interfaccia.

Il logger ha una finestra nascosta col titolo legato al suo database: la si
trova per nome e le si manda un messaggio. Niente file o porte da gestire.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .launcher import logger_key

CLASS_NAME = "TimeScreenTray"
WM_CONTROL = 0x8000 + 2  # WM_APP + 2
CMD_RESUME, CMD_PAUSE, CMD_QUERY = 0, 1, 2
SMTO_BLOCK, SMTO_ABORTIFHUNG = 0x1, 0x2

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t),
]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t


def window_title() -> str:
    return f"TimeScreen logger {logger_key()}"


def _send(cmd: int) -> int | None:
    hwnd = user32.FindWindowW(CLASS_NAME, window_title())
    if not hwnd:
        return None
    result = ctypes.c_size_t(0)
    ok = user32.SendMessageTimeoutW(hwnd, WM_CONTROL, cmd, 0, SMTO_BLOCK | SMTO_ABORTIFHUNG, 2000, ctypes.byref(result))
    return result.value if ok else None


def _state(reply: int | None) -> str:
    if reply is None:
        return "stopped"
    return "paused" if reply == 1 else "running"


def status() -> str:
    """'running', 'paused' oppure 'stopped' (logger non avviato)."""
    return _state(_send(CMD_QUERY))


def set_paused(paused: bool) -> str:
    return _state(_send(CMD_PAUSE if paused else CMD_RESUME))
