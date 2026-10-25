"""Come riavviare TimeScreen stesso, sia da sorgente sia dall'exe impacchettato."""

from __future__ import annotations

import ctypes
import hashlib
import subprocess
import sys
from pathlib import Path

from .db import default_path

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "TimeScreen.App"  # raggruppa le finestre sulla barra delle applicazioni con la nostra icona

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


def frozen() -> bool:
    return getattr(sys, "frozen", False)


def self_command(*args: str) -> list[str]:
    """La riga di comando per lanciare TimeScreen con questi argomenti, senza console."""
    if frozen():
        return [sys.executable, *args]
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else exe), "-m", "timescreen", *args]


def spawn(*args: str) -> None:
    """Avvia un'altra istanza di TimeScreen staccata da questa."""
    subprocess.Popen(
        self_command(*args),
        cwd=None if frozen() else ROOT,
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )


def logger_mutex_name() -> str:
    # un solo logger per database (un database di prova può averne un altro)
    key = hashlib.sha1(str(default_path()).lower().encode()).hexdigest()[:12]
    return f"Local\\TimeScreenLogger-{key}"


def logger_running() -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenMutexW.restype = ctypes.c_void_p
    kernel32.OpenMutexW.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenMutexW(0x00100000, False, logger_mutex_name())  # SYNCHRONIZE
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def set_app_id() -> None:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(APP_ID))
