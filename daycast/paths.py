"""Dove stanno i dati: %LOCALAPPDATA%\\Daycast.

Prima di chiamarsi Daycast l'app usava %LOCALAPPDATA%\\TimeScreen: al primo
avvio la cartella vecchia viene rinominata, così storico e categorie restano.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Daycast"
OLD_APP_NAME = "TimeScreen"


def data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or str(Path.home()))
    folder = base / APP_NAME
    old = base / OLD_APP_NAME
    if not folder.exists() and old.exists():
        try:
            old.rename(folder)
        except OSError:
            # file ancora aperti (es. il vecchio logger in esecuzione): si continua a usare la vecchia
            return old
    return folder


def env_path(name: str) -> Path | None:
    """Percorso da variabile d'ambiente, per prove e sviluppo (DAYCAST_*, o il vecchio TIMESCREEN_*)."""
    value = os.environ.get(f"DAYCAST_{name}") or os.environ.get(f"TIMESCREEN_{name}")
    return Path(value) if value else None
