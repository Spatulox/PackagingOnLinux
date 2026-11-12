"""AppImage, Flatpak and Snap backends."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from packagingonlinux import core
from packagingonlinux.backend import BuildContext
from packagingonlinux.linux import appimage, staging


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
