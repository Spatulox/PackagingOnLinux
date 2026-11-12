from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from packagingonlinux import config


def make_png(path: Path, width: int, height: int) -> Path:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    path.write_bytes(png)
    return path


@pytest.fixture
def hello_project(tmp_path: Path) -> Path:
    """A tiny project: shell-script app + 64x64 icon + packaging.toml. Returns the config path."""
    app = tmp_path / "hello"
    app.write_text("#!/bin/sh\necho 'Hello from PackagingOnLinux'\n")
    app.chmod(0o755)
    make_png(tmp_path / "hello.png", 64, 64)
    (tmp_path / "packaging.toml").write_text(
        '[app]\n'
        'id = "org.example.Hello"\n'
        'name = "Hello"\n'
        'version = "1.2.3"\n'
        'summary = "Says hello"\n'
        'description = "A tiny test application.\\n\\nSecond paragraph."\n'
        'license = "MIT"\n'
        'maintainer = "Test <test@example.org>"\n'
        'categories = ["Utility"]\n'
        '\n[files]\nbinary = "hello"\nicon = "hello.png"\n'
        '\n[output]\nformats = ["deb", "tarball"]\ndir = "out"\n'
    )
    return tmp_path / "packaging.toml"


@pytest.fixture
def hello_spec(hello_project: Path) -> config.AppSpec:
    return config.load(hello_project)


def make_pe(path: Path, machine: int = 0x8664) -> Path:
    """A minimal file with a valid PE header (DOS stub -> "PE\\0\\0" -> machine type)."""
    dos = bytearray(64)
    dos[:2] = b"MZ"
    dos[0x3C:0x40] = struct.pack("<I", 64)
    path.write_bytes(bytes(dos) + b"PE\0\0" + struct.pack("<H", machine) + b"\0" * 18)
    return path


@pytest.fixture
def windows_spec(hello_spec: config.AppSpec) -> config.AppSpec:
    """hello_spec plus a [windows] target: a fake x64 hello.exe (the icon comes from [linux])."""
    exe = make_pe(hello_spec.base_dir / "hello.exe")
    hello_spec.windows = config.Target(binary=exe)
    return hello_spec
