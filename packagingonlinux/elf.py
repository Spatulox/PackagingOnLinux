"""Detect a binary's CPU architecture from its ELF header (no external tools)."""

from __future__ import annotations

import struct
from pathlib import Path

# e_machine -> (debian arch, rpm arch)
_MACHINES = {
    0x03: ("i386", "i686"),
    0x28: ("armhf", "armv7hl"),
    0x3E: ("amd64", "x86_64"),
    0xB7: ("arm64", "aarch64"),
    0xF3: ("riscv64", "riscv64"),
    0x15: ("ppc64el", "ppc64le"),
    0x16: ("s390x", "s390x"),
}

ARCH_INDEPENDENT = ("all", "noarch")


def is_elf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


def detect_arch(path: Path) -> tuple[str, str]:
    """Return (deb_arch, rpm_arch). Non-ELF files (scripts) are architecture independent."""
    try:
        with open(path, "rb") as f:
            header = f.read(20)
    except OSError:
        return ARCH_INDEPENDENT
    if len(header) < 20 or header[:4] != b"\x7fELF":
        return ARCH_INDEPENDENT
    endian = "<" if header[5] == 1 else ">"
    (machine,) = struct.unpack(endian + "H", header[18:20])
    if machine not in _MACHINES:
        raise ValueError(f"{path}: unsupported ELF machine type 0x{machine:x}")
    return _MACHINES[machine]
