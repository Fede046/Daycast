"""Avvio automatico del logger all'accesso a Windows (solo per l'utente corrente)."""

from __future__ import annotations

import subprocess
import winreg
from pathlib import Path

from .launcher import frozen, self_command

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "TimeScreen Logger"
LAUNCHER = Path(__file__).resolve().parent.parent / "timescreen_logger.pyw"


def command() -> str:
    if frozen():
        return subprocess.list2cmdline(self_command("log"))
    # da sorgente: -m non funziona all'accesso (la cartella di lavoro è un'altra),
    # quindi passa da un piccolo file che sa dove si trova il progetto
    pythonw = self_command()[0]
    return subprocess.list2cmdline([pythonw, str(LAUNCHER)])


def current() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)[0]
    except FileNotFoundError:
        return None


def is_enabled() -> bool:
    return current() is not None


def enable() -> str:
    cmd = command()
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    return cmd


def disable() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
