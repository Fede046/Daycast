# -*- mode: python -*-
# Spec di PyInstaller: una cartella con TimeScreen.exe (avvio veloce, niente
# estrazione in una cartella temporanea a ogni apertura). Si usa da build.py.

from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "timescreen"

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    datas=[
        (str(PKG / "ui"), "timescreen/ui"),
        (str(PKG / "assets"), "timescreen/assets"),
    ],
    excludes=["tkinter", "unittest", "pydoc", "test"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TimeScreen",
    icon=str(PKG / "assets" / "icon.ico"),
    version=str(ROOT / "build" / "version_info.txt"),
    console=False,  # nessuna finestra nera
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="TimeScreen", upx=False)
