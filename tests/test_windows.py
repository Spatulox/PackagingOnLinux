from __future__ import annotations

import shutil
import struct
import zipfile
from pathlib import Path

import pytest

from packagingonlinux import config, core, ico, pe, winstage
from packagingonlinux.backends.nsis import esc, nsis_script, product_version, shortcut_name
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


# ---- NSIS installer -----------------------------------------------------------

def _script(spec, files: dict[str, str] | None = None, arch: str = "x64") -> str:
    files = files or {"hello.exe": "/p/00000", "hello.ico": "/p/00001"}
    payload = {rel: Path(src) for rel, src in files.items()}
    icon = payload.get("hello.ico")
    return nsis_script(spec, payload, icon, Path("/out/Hello-setup.exe"), arch, 42)


def test_nsis_escaping():
    assert esc('a $b "c"\nd') == 'a $$b $\\"c$\\"$\\nd'
    assert product_version("1.2.3") == "1.2.3.0"
    assert product_version("2024.10+git~1") == "2024.10.0.0"
    assert shortcut_name('A/B: "C"?') == "AB C"


def test_nsis_script_installs_per_user(windows_spec):
    windows_spec.maintainer = 'Jane "J" Doe <j@d.org>'
    text = _script(windows_spec)
    assert "RequestExecutionLevel user\n" in text
    assert 'InstallDir "$LOCALAPPDATA\\Programs\\Hello"' in text
    assert '!define MUI_ICON "/p/00001"' in text
    assert '  File "/oname=hello.exe" "/p/00000"\n' in text
    key = '"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\org.example.Hello"'
    assert f'WriteRegStr HKCU {key} "DisplayVersion" "1.2.3"' in text
    assert f'WriteRegStr HKCU {key} "Publisher" "Jane $\\"J$\\" Doe"' in text
    assert f'WriteRegStr HKCU {key} "DisplayIcon" "$INSTDIR\\hello.ico"' in text
    assert f'WriteRegDWORD HKCU {key} "EstimatedSize" 42' in text
    assert "HKLM" not in text and "${RunningX64}" in text


def test_nsis_uninstaller_removes_exactly_what_it_installed(windows_spec):
    windows_spec.windows = config.Target(dir=Path("/dist"), exec="bin/app.exe")
    text = _script(windows_spec, {"bin/app.exe": "/p/0", "bin/lib/x $1.dll": "/p/1", "readme.txt": "/p/2"})
    assert '  SetOutPath "$INSTDIR\\bin\\lib"\n  File "/oname=x $$1.dll" "/p/1"\n' in text
    uninstall = text[text.index('Section "Uninstall"'):]
    assert uninstall.index('RMDir "$INSTDIR\\bin\\lib"') < uninstall.index('RMDir "$INSTDIR\\bin"') \
        < uninstall.index('RMDir "$INSTDIR"')
    assert 'Delete "$INSTDIR\\bin\\lib\\x $$1.dll"' in uninstall
    assert "/r" not in uninstall
    assert "MUI_ICON" not in text  # no icon: shortcuts use the exe's own
    assert '"$INSTDIR\\bin\\app.exe" "" "$INSTDIR\\bin\\app.exe" 0' in text


@pytest.mark.skipif(not shutil.which("makensis"), reason="makensis missing (apt install nsis)")
def test_build_nsis_installer(windows_spec):
    windows_spec.name = "Hello Wörld"  # non-ASCII name, spaces in file names
    result = core.build(windows_spec, ["nsis"], log=lambda _: None)
    assert result.ok, result.errors
    out = result.packages["nsis"][0]
    assert out.name == "Hello-Wörld-1.2.3-windows-x64-setup.exe"
    assert pe.detect_arch(out) == "x86"  # the NSIS stub itself runs everywhere
