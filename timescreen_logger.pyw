"""Avvia il logger senza console; è il file che parte all'accesso a Windows."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from timescreen.cli import main  # noqa: E402

main(["log"])
