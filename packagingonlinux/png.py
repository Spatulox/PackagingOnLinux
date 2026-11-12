"""PNG header reading, shared by the Linux (hicolor size) and Windows (.ico) icon code."""

from __future__ import annotations

import struct
from pathlib import Path


def png_size(path: Path) -> tuple[int, int] | None:
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])
