"""Detect a Windows executable's CPU architecture from its PE header (no external tools).

Layout: "MZ" DOS header, whose 32-bit field at 0x3C points to the "PE\\0\\0" signature,
followed by the COFF header whose first field is the machine type.
"""

from __future__ import annotations

import struct
from pathlib import Path

# COFF machine type -> architecture name used in file names (and by NSIS/Windows docs)
_MACHINES = {
    0x014C: "x86",
    0x8664: "x64",
    0xAA64: "arm64",
}


def _machine(path: Path) -> int | None:
    """The COFF machine type, or None if `path` is not a PE file."""
    try:
        with open(path, "rb") as f:
            dos = f.read(64)
            if len(dos) < 64 or dos[:2] != b"MZ":
                return None
            (offset,) = struct.unpack("<I", dos[0x3C:0x40])
            f.seek(offset)
            header = f.read(6)
    except OSError:
        return None
    if len(header) < 6 or header[:4] != b"PE\0\0":
        return None
    return struct.unpack("<H", header[4:6])[0]


def is_pe(path: Path) -> bool:
    return _machine(path) is not None


def detect_arch(path: Path) -> str:
    """Return "x86", "x64" or "arm64". Raises ValueError for non-PE files."""
    machine = _machine(path)
    if machine is None:
        raise ValueError(f"{path}: not a Windows executable (no PE header)")
    if machine not in _MACHINES:
        raise ValueError(f"{path}: unsupported PE machine type 0x{machine:x}")
    return _MACHINES[machine]
