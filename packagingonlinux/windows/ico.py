"""Produce the Windows .ico used by shortcuts and the installer, in pure Python.

Since Windows Vista an .ico entry may hold PNG data as is, so a square PNG of at most
256 px only needs a 22-byte ICO header in front of it. Anything else (SVG, non-square or
larger PNG) would need resampling, which this tool doesn't do: the user is asked for an
.ico instead.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

from packagingonlinux.png import png_size

ICO_MAGIC = b"\0\0\1\0"


def png_to_ico(png: bytes, size: int) -> bytes:
    """Wrap PNG data in a single-entry ICO container (width/height byte 0 means 256)."""
    dim = 0 if size == 256 else size
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), 6 + 16)
    return header + entry + png


def make_ico(src: Path, dest: Path) -> list[str]:
    """Write `dest` from an .ico or PNG `src`. Returns warnings; on a warning no file is written."""
    suffix = src.suffix.lower()
    if suffix == ".ico":
        with open(src, "rb") as f:
            if f.read(4) != ICO_MAGIC:
                return [f"{src} is not a valid .ico file: Windows packages get no custom icon"]
        shutil.copyfile(src, dest)
        return []
    size = png_size(src) if suffix == ".png" else None
    if size is None:
        return [f"Windows needs an .ico or PNG icon, not {src.name}: set [windows] icon to an .ico file"]
    w, h = size
    if w != h or w > 256:
        return [f"icon is {w}x{h}: Windows packages need a square PNG of at most 256 px, "
                "or an .ico file in [windows] icon; using no custom icon"]
    dest.write_bytes(png_to_ico(src.read_bytes(), w))
    return []
