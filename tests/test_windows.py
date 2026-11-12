from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from packagingonlinux import config, core, ico, pe, winstage
from tests.conftest import make_pe, make_png


@pytest.mark.parametrize("machine,expected", [(0x14C, "x86"), (0x8664, "x64"), (0xAA64, "arm64")])
def test_detect_pe_arch(tmp_path: Path, machine, expected):
    assert pe.detect_arch(make_pe(tmp_path / "app.exe", machine)) == expected


def test_non_pe_is_rejected(hello_spec):
    assert not pe.is_pe(hello_spec.linux.binary)
    with pytest.raises(ValueError, match="not a Windows executable"):
        pe.detect_arch(hello_spec.linux.binary)


def test_png_is_wrapped_in_ico(tmp_path: Path):
    png = make_png(tmp_path / "icon.png", 256, 256)
    assert ico.make_ico(png, tmp_path / "icon.ico") == []
    data = (tmp_path / "icon.ico").read_bytes()
    reserved, kind, count, width, height = struct.unpack("<HHHBB", data[:8])
    assert (reserved, kind, count, width, height) == (0, 1, 1, 0, 0)  # 0 = 256 px
    size, offset = struct.unpack("<II", data[14:22])
    assert offset == 22 and data[22:] == png.read_bytes() and size == len(data) - 22


@pytest.mark.parametrize("width,height", [(50, 60), (512, 512)])
def test_unusable_png_gives_a_warning_and_no_icon(tmp_path: Path, width, height):
    png = make_png(tmp_path / "icon.png", width, height)
    warnings = ico.make_ico(png, tmp_path / "icon.ico")
    assert "square PNG of at most 256" in warnings[0]
    assert not (tmp_path / "icon.ico").exists()


def test_ico_is_copied_as_is(tmp_path: Path):
    src = tmp_path / "in.ico"
    src.write_bytes(ico.png_to_ico(make_png(tmp_path / "i.png", 32, 32).read_bytes(), 32))
    assert ico.make_ico(src, tmp_path / "out.ico") == []
    assert (tmp_path / "out.ico").read_bytes() == src.read_bytes()


def test_windows_stage(windows_spec, tmp_path: Path):
    assert winstage.build_stage(windows_spec, tmp_path / "stage") == []
    assert winstage.installed_files(tmp_path / "stage") == ["hello.exe", "hello.ico"]
    assert windows_spec.windows_arch == "x64"


def test_build_zip(windows_spec):
    result = core.build(windows_spec, ["zip"], log=lambda _: None)
    assert result.ok, result.errors
    out = result.packages["zip"][0]
    assert out.name == "Hello-1.2.3-windows-x64.zip"
    assert sorted(zipfile.ZipFile(out).namelist()) == ["Hello/hello.exe", "Hello/hello.ico"]


def test_windows_only_config_needs_no_linux_target(windows_spec):
    windows_spec.linux = None  # no [linux]: no icon to borrow either
    logs: list[str] = []
    result = core.build(windows_spec, ["zip"], log=logs.append)
    assert result.ok, result.errors
    assert any("no icon set" in line for line in logs)


def test_directory_app(windows_spec, tmp_path: Path):
    app = tmp_path / "dist-win"
    (app / "bin").mkdir(parents=True)
    make_pe(app / "bin/app.exe", 0xAA64)
    (app / "data.txt").write_text("x")
    windows_spec.windows = config.Target(dir=app, exec="bin/app.exe")
    result = core.build(windows_spec, ["zip"], log=lambda _: None)
    assert result.ok, result.errors
    out = result.packages["zip"][0]
    assert out.name == "Hello-1.2.3-windows-arm64.zip"
    assert sorted(zipfile.ZipFile(out).namelist()) == [
        "Hello/bin/app.exe", "Hello/data.txt", "Hello/hello.ico"]


def test_linux_binary_given_as_windows_target_fails_the_windows_formats(windows_spec):
    windows_spec.windows.binary = windows_spec.linux.binary
    result = core.build(windows_spec, ["zip", "tarball"], log=lambda _: None)
    assert "not a Windows executable" in result.errors["zip"]
    assert "tarball" in result.packages
