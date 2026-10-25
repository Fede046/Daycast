"""Costruisce l'app da distribuire: dist/TimeScreen/TimeScreen.exe e lo zip.

    .venv\\Scripts\\pip install -r requirements-dev.txt
    .venv\\Scripts\\python packaging\\build.py
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from timescreen import __version__  # noqa: E402

BUILD = ROOT / "build"
DIST = ROOT / "dist"

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041004b0', [
      StringStruct('CompanyName', 'TimeScreen'),
      StringStruct('FileDescription', 'TimeScreen'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'TimeScreen'),
      StringStruct('OriginalFilename', 'TimeScreen.exe'),
      StringStruct('ProductName', 'TimeScreen'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [0x0410, 1200])])
  ]
)
"""


def main() -> None:
    import PyInstaller.__main__

    BUILD.mkdir(exist_ok=True)
    # nome e versione dentro l'exe: li mostrano Gestione attività e le proprietà del file
    parts = [int(x) for x in __version__.split(".")] + [0]
    (BUILD / "version_info.txt").write_text(
        VERSION_INFO.format(t=tuple(parts[:4]), v=__version__), encoding="utf-8"
    )

    PyInstaller.__main__.run([
        str(ROOT / "packaging" / "TimeScreen.spec"),
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
    ])

    app_dir = DIST / "TimeScreen"
    zip_path = DIST / f"TimeScreen-{__version__}-win64.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(app_dir.rglob("*")):
            zf.write(f, Path("TimeScreen") / f.relative_to(app_dir))
    size = zip_path.stat().st_size / 1e6
    print(f"\nPronto: {app_dir / 'TimeScreen.exe'}\n        {zip_path}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
