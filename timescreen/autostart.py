"""Avvio automatico del logger all'accesso a Windows (solo per l'utente corrente).

La voce va in HKCU\\...\\Run, così compare anche in Impostazioni → App → Avvio
e in Gestione attività → App di avvio. Da lì l'utente può spegnerla: Windows
lo segna in StartupApproved\\Run (primo byte dispari = disattivata) senza
togliere la voce, quindi per sapere se è attiva vanno guardati tutti e due.
"""

from __future__ import annotations

import subprocess
import winreg
from pathlib import Path

from .launcher import frozen, self_command

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
VALUE_NAME = "TimeScreen"
OLD_VALUE_NAMES = ["TimeScreen Logger"]  # nomi usati dalle versioni precedenti
LAUNCHER = Path(__file__).resolve().parent.parent / "timescreen_logger.pyw"


def command() -> str:
    if frozen():
        return subprocess.list2cmdline(self_command("log"))
    # da sorgente: -m non funziona all'accesso (la cartella di lavoro è un'altra),
    # quindi passa da un piccolo file che sa dove si trova il progetto
    pythonw = self_command()[0]
    return subprocess.list2cmdline([pythonw, str(LAUNCHER)])


def _read(key_path: str, name: str):
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


def _delete(key_path: str, name: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
        return True
    except FileNotFoundError:
        return False


def current() -> str | None:
    """Il comando registrato per l'avvio, se c'è."""
    for name in [VALUE_NAME, *OLD_VALUE_NAMES]:
        value = _read(RUN_KEY, name)
        if value:
            return value
    return None


def _disabled_in_windows(name: str) -> bool:
    flags = _read(APPROVED_KEY, name)
    return isinstance(flags, bytes) and len(flags) > 0 and flags[0] % 2 == 1


def is_enabled() -> bool:
    for name in [VALUE_NAME, *OLD_VALUE_NAMES]:
        if _read(RUN_KEY, name) and not _disabled_in_windows(name):
            return True
    return False


def enable() -> str:
    cmd = command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    # se era stata spenta da Impostazioni di Windows, riaccenderla anche lì
    _delete(APPROVED_KEY, VALUE_NAME)
    for old in OLD_VALUE_NAMES:
        _delete(RUN_KEY, old)
        _delete(APPROVED_KEY, old)
    return cmd


def disable() -> bool:
    removed = False
    for name in [VALUE_NAME, *OLD_VALUE_NAMES]:
        removed |= _delete(RUN_KEY, name)
        _delete(APPROVED_KEY, name)
    return removed
