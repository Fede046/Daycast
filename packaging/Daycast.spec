# -*- mode: python -*-
# Spec di PyInstaller: una cartella con Daycast.exe (avvio veloce, niente
# estrazione in una cartella temporanea a ogni apertura). Si usa da build.py,
# che prima scarica il modello Timestral-5M in daycast/models.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "daycast"
MODEL = PKG / "models" / "Timestral-5M"

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(PKG / "ui"), "daycast/ui"),
        (str(PKG / "assets"), "daycast/assets"),
        # il modello va nell'app: nessun download, nessuna connessione
        *[(str(MODEL / f), "daycast/models/Timestral-5M") for f in ("config.json", "model.safetensors", "LICENSE")],
    ],
    # forecast.py importa torch e timestral solo dentro le funzioni
    hiddenimports=["daycast.forecast", *collect_submodules("timestral")],
    # unittest no: PyTorch lo importa all'avvio; hf_xet serve solo per scaricare, il modello è incluso
    excludes=["tkinter", "pydoc", "test", "hf_xet"],
)


def _needed(entry) -> bool:
    # di PyTorch servono le DLL, non le librerie statiche (.lib), gli header o i file per CMake
    dest = entry[0].replace("\\", "/").lower()
    if dest.startswith("torch/"):
        return not (dest.endswith(".lib") or "/include/" in dest or "/share/cmake/" in dest)
    return True


a.binaries = [b for b in a.binaries if _needed(b)]
a.datas = [d for d in a.datas if _needed(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Daycast",
    icon=str(PKG / "assets" / "icon.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
    console=False,  # nessuna finestra nera
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Daycast", upx=False)
