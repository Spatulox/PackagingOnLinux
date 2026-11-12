"""AppImage, Flatpak and Snap backends."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from packagingonlinux import core
from packagingonlinux.backend import BuildContext
from packagingonlinux.linux import appimage, flatpak, staging
from tests.conftest import make_png


def _ctx(spec, tmp_path: Path) -> BuildContext:
    stage = tmp_path / "stage"
    staging.build_stage(spec, stage)
    workdir = tmp_path / "work"
    workdir.mkdir()
    return BuildContext(spec, stage, workdir, tmp_path / "out", lambda _: None)


# ---- AppImage ----------------------------------------------------------------

def test_appdir_layout(hello_spec, tmp_path):
    ctx = _ctx(hello_spec, tmp_path)
    appdir = tmp_path / "AppDir"
    appimage.make_appdir(ctx, appdir)
    assert (appdir / "AppRun").is_symlink()
    assert (appdir / "AppRun").resolve() == (appdir / "usr/bin/hello").resolve()
    assert (appdir / "org.example.Hello.desktop").read_text() == \
        (appdir / "usr/share/applications/org.example.Hello.desktop").read_text()
    assert (appdir / "org.example.Hello.png").is_file()
    assert (appdir / ".DirIcon").resolve() == (appdir / "org.example.Hello.png").resolve()


def test_appimage_arch():
    class Spec:
        def __init__(self, arch):
            self.linux_arch = ("x", arch)
    assert appimage.appimage_arch(Spec("aarch64"), print) == "aarch64"
    assert appimage.appimage_arch(Spec("armv7hl"), print) == "armhf"
    with pytest.raises(ValueError):
        appimage.appimage_arch(Spec("s390x"), print)


def test_appimage_runtime_checksum_is_verified(tmp_path, monkeypatch):
    monkeypatch.delenv(appimage.RUNTIME_ENV, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    (tmp_path / f"runtime-{appimage.RUNTIME_RELEASE}-x86_64").write_bytes(b"not the runtime")
    monkeypatch.setattr(appimage, "RUNTIME_URL", f"file://{tmp_path}/runtime-{{release}}-{{arch}}")
    with pytest.raises(ValueError, match="sha256"):
        appimage.runtime("x86_64", lambda _: None)
    assert not list((tmp_path / "packagingonlinux").iterdir())


@pytest.mark.skipif(not shutil.which("mksquashfs"), reason="squashfs-tools missing")
def test_build_appimage(hello_spec, tmp_path, monkeypatch):
    fake_runtime = tmp_path / "runtime"
    fake_runtime.write_bytes(b"\x7fELF fake runtime")
    monkeypatch.setenv(appimage.RUNTIME_ENV, str(fake_runtime))
    result = core.build(hello_spec, ["appimage"], log=lambda _: None)
    assert result.ok, result.errors
    out = result.packages["appimage"][0]
    assert out.name.startswith("Hello-1.2.3-") and out.name.endswith(".AppImage")
    assert out.stat().st_mode & 0o111
    data = out.read_bytes()
    offset = len(fake_runtime.read_bytes())
    assert data[:offset] == fake_runtime.read_bytes() and data[offset:offset + 4] == b"hsqs"
    if shutil.which("unsquashfs"):
        listing = subprocess.run(["unsquashfs", "-o", str(offset), "-l", str(out)],
                                 capture_output=True, text=True, check=True).stdout
        for name in ("AppRun", ".DirIcon", "org.example.Hello.desktop", "usr/bin/hello"):
            assert f"squashfs-root/{name}" in listing


# ---- Flatpak -----------------------------------------------------------------

def test_flatpak_manifest(hello_spec, tmp_path):
    hello_spec.flatpak.finish_args = ["--socket=wayland", "--filesystem=home"]
    m = flatpak.manifest(hello_spec, tmp_path / "src")
    assert m["id"] == "org.example.Hello" and m["command"] == "hello"
    assert (m["runtime"], m["runtime-version"], m["sdk"]) == (
        "org.freedesktop.Platform", hello_spec.flatpak.runtime_version, "org.freedesktop.Sdk")
    assert m["finish-args"] == ["--socket=wayland", "--filesystem=home"]
    module = m["modules"][0]
    assert module["sources"] == [{"type": "dir", "path": str(tmp_path / "src")}]
    assert module["build-commands"] == ["cp -a usr/. /app/"]
    json.dumps(m)


def test_flatpak_sdk_follows_runtime(hello_spec):
    hello_spec.flatpak.runtime = "org.kde.Platform"
    assert hello_spec.flatpak.sdk_name == "org.kde.Sdk"
    hello_spec.flatpak.sdk = "org.example.Sdk"
    assert hello_spec.flatpak.sdk_name == "org.example.Sdk"


def test_flatpak_rejects_pixmaps_icon(hello_spec):
    make_png(hello_spec.linux.icon, 50, 60)
    with pytest.raises(ValueError, match="square icon"):
        flatpak.check(hello_spec)


def test_flatpak_rejects_dash_before_last_id_part(hello_spec):
    flatpak.check(hello_spec)
    hello_spec.id = "org.my-site.Hello"
    with pytest.raises(ValueError, match="last part"):
        flatpak.check(hello_spec)
