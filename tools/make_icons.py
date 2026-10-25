"""Genera il logo provvisorio: icone .ico per l'area di notifica e .svg per la UI.

Solo libreria standard: il disegno è semplice (quadrato arrotondato con una
linea che sale) e viene rasterizzato a mano con un po' di antialiasing.

    python tools/make_icons.py
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "timescreen" / "assets"
UI = ROOT / "timescreen" / "ui"

# disegno su una griglia 24x24
RECT = (1.0, 1.0, 23.0, 23.0)
RADIUS = 5.5
LINE = [(5.5, 16.0), (10.0, 11.5), (13.5, 14.5), (18.5, 8.5)]

ACTIVE = (0x2A, 0x78, 0xD6)  # blu della palette
PAUSED = (0x89, 0x87, 0x81)  # grigio: registrazione in pausa
SIZES = [16, 20, 24, 32, 40, 48, 64]


def _in_rrect(u: float, v: float) -> bool:
    x0, y0, x1, y1 = RECT
    dx = max(x0 + RADIUS - u, 0.0, u - (x1 - RADIUS))
    dy = max(y0 + RADIUS - v, 0.0, v - (y1 - RADIUS))
    return x0 <= u <= x1 and y0 <= v <= y1 and dx * dx + dy * dy <= RADIUS * RADIUS


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    vx, vy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _near_line(u: float, v: float, width: float) -> bool:
    return any(_seg_dist(u, v, *LINE[i], *LINE[i + 1]) <= width / 2 for i in range(len(LINE) - 1))


def render(size: int, bg: tuple[int, int, int]) -> bytes:
    """Pixel BGRA dall'alto in basso."""
    ss = 4  # campioni per lato, per l'antialiasing
    width = 3.0 if size <= 20 else 2.6  # linea un po' più spessa nelle icone piccole
    out = bytearray()
    for y in range(size):
        for x in range(size):
            inside = line = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (x + (sx + 0.5) / ss) * 24 / size
                    v = (y + (sy + 0.5) / ss) * 24 / size
                    if _in_rrect(u, v):
                        inside += 1
                        if _near_line(u, v, width):
                            line += 1
            alpha = inside / (ss * ss)
            mix = line / inside if inside else 0.0
            r, g, b = (round(c + (255 - c) * mix) for c in bg)
            out += bytes((b, g, r, round(alpha * 255)))
    return bytes(out)


def write_ico(path: Path, bg: tuple[int, int, int]) -> None:
    images = []
    for size in SIZES:
        pixels = render(size, bg)
        rows = [pixels[i * size * 4:(i + 1) * size * 4] for i in range(size)]
        bmp = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
        bmp += b"".join(reversed(rows))  # le BMP vanno dal basso verso l'alto
        mask_row = ((size + 31) // 32) * 4
        bmp += b"\x00" * mask_row * size  # maschera AND vuota: conta il canale alfa
        images.append((size, bmp))

    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries = b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b"".join(d for _, d in images))


def svg(bg: tuple[int, int, int]) -> str:
    color = "#{:02x}{:02x}{:02x}".format(*bg)
    x0, y0, x1, y1 = RECT
    points = " ".join(f"{x:g},{y:g}" for x, y in LINE)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<rect x="{x0:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" rx="{RADIUS:g}" fill="{color}"/>'
        f'<polyline points="{points}" fill="none" stroke="#fff" stroke-width="2.6" '
        'stroke-linecap="round" stroke-linejoin="round"/></svg>\n'
    )


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    write_ico(ASSETS / "icon.ico", ACTIVE)
    write_ico(ASSETS / "icon-paused.ico", PAUSED)
    (UI / "logo.svg").write_text(svg(ACTIVE), encoding="utf-8")
    print("icone scritte in", ASSETS, "e", UI / "logo.svg")


if __name__ == "__main__":
    main()
