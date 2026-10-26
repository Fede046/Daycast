"""Genera il logo di Daycast: icone .ico per l'area di notifica e l'exe, .svg per la UI.

Il disegno: un sole che sorge sopra tre barre (il "meteo" della giornata al PC),
su un quadrato arrotondato color ambra. Solo libreria standard: il disegno
viene rasterizzato a mano, con un po' di antialiasing.

    python tools/make_icons.py
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "daycast" / "assets"
UI = ROOT / "daycast" / "ui"

# disegno su una griglia 24x24
RECT = (1.0, 1.0, 23.0, 23.0)
RADIUS = 5.5
SUN = (12.0, 11.5, 4.5)  # centro e raggio: si vede la metà superiore
RAYS = [((12, 4.6), (12, 6.2)), ((6.6, 6.6), (7.7, 7.7)), ((17.4, 6.6), (16.3, 7.7)),
        ((4.5, 11.5), (5.9, 11.5)), ((18.1, 11.5), (19.5, 11.5))]
RAY_WIDTH = 1.4
BARS = [(6.0, 14.0, 3.0, 5.0), (10.5, 13.0, 3.0, 6.0), (15.0, 15.5, 3.0, 3.5)]  # x, y, larghezza, altezza
BAR_RADIUS = 1.0

ACTIVE = (0xEF, 0x9F, 0x27)  # ambra
PAUSED = (0x89, 0x87, 0x81)  # grigio: registrazione in pausa
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def _in_rrect(u, v, x0, y0, x1, y1, r) -> bool:
    if not (x0 <= u <= x1 and y0 <= v <= y1):
        return False
    dx = max(x0 + r - u, 0.0, u - (x1 - r))
    dy = max(y0 + r - v, 0.0, v - (y1 - r))
    return dx * dx + dy * dy <= r * r


def _seg_dist(px, py, a, b) -> float:
    (ax, ay), (bx, by) = a, b
    vx, vy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _white(u, v, size) -> bool:
    cx, cy, r = SUN
    if v <= cy and math.hypot(u - cx, v - cy) <= r:
        return True
    # nelle icone piccolissime i raggi diventano rumore
    if size >= 20 and any(_seg_dist(u, v, a, b) <= RAY_WIDTH / 2 for a, b in RAYS):
        return True
    return any(_in_rrect(u, v, x, y, x + w, y + h, BAR_RADIUS) for x, y, w, h in BARS)


def render(size: int, bg: tuple[int, int, int]) -> bytes:
    """Pixel BGRA dall'alto in basso."""
    ss = 4  # campioni per lato, per l'antialiasing
    out = bytearray()
    for y in range(size):
        for x in range(size):
            inside = white = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (x + (sx + 0.5) / ss) * 24 / size
                    v = (y + (sy + 0.5) / ss) * 24 / size
                    if _in_rrect(u, v, *RECT, RADIUS):
                        inside += 1
                        if _white(u, v, size):
                            white += 1
            alpha = inside / (ss * ss)
            mix = white / inside if inside else 0.0
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
    cx, cy, r = SUN
    rays = "".join(f"M{a[0]:g} {a[1]:g}L{b[0]:g} {b[1]:g}" for a, b in RAYS)
    bars = "".join(
        f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{BAR_RADIUS:g}" fill="#fff"/>' for x, y, w, h in BARS
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<rect x="{x0:g}" y="{y0:g}" width="{x1 - x0:g}" height="{y1 - y0:g}" rx="{RADIUS:g}" fill="{color}"/>'
        f'<path d="M{cx - r:g} {cy:g}a{r:g} {r:g} 0 0 1 {2 * r:g} 0z" fill="#fff"/>'
        f'<path d="{rays}" stroke="#fff" stroke-width="{RAY_WIDTH:g}" stroke-linecap="round"/>'
        f"{bars}</svg>\n"
    )


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    write_ico(ASSETS / "icon.ico", ACTIVE)
    write_ico(ASSETS / "icon-paused.ico", PAUSED)
    (UI / "logo.svg").write_text(svg(ACTIVE), encoding="utf-8")
    print("icone scritte in", ASSETS, "e", UI / "logo.svg")


if __name__ == "__main__":
    main()
