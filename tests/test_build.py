from __future__ import annotations

import os
import shutil
import subprocess
import tarfile

import pytest

from packagingonlinux import core, staging
from packagingonlinux.backends.base import BuildContext
from packagingonlinux.backends.rpm import spec_file
from tests.conftest import make_png


def test_stage_layout(hello_spec, tmp_path):
    root = tmp_path / "stage"
    assert staging.build_stage(hello_spec, root) == []
    assert staging.installed_files(root) == [
        "/usr/bin/hello",
        "/usr/share/applications/org.example.Hello.desktop",
        "/usr/share/icons/hicolor/64x64/apps/org.example.Hello.png",
        "/usr/share/metainfo/org.example.Hello.metainfo.xml",
    ]
    desktop = (root / "usr/share/applications/org.example.Hello.desktop").read_text()
    assert "Exec=hello\n" in desktop and "Icon=org.example.Hello\n" in desktop
    assert (root / "usr/bin/hello").stat().st_mode & 0o777 == 0o755


def test_non_square_icon_goes_to_pixmaps(hello_spec, tmp_path):
    make_png(hello_spec.icon, 50, 60)
    warnings = staging.build_stage(hello_spec, tmp_path / "stage")
    assert (tmp_path / "stage/usr/share/pixmaps/org.example.Hello.png").exists()
    assert "square" in warnings[0]


def test_directory_app_uses_symlink(hello_spec, tmp_path):
    appdir = tmp_path / "dist"
    (appdir / "bin").mkdir(parents=True)
    shutil.copy2(hello_spec.binary, appdir / "bin/hello")
    (appdir / "data.txt").write_text("x")
    hello_spec.binary, hello_spec.dir, hello_spec.exec = None, appdir, "bin/hello"
    root = tmp_path / "stage"
    staging.build_stage(hello_spec, root)
    link = root / "usr/bin/hello"
    assert link.is_symlink() and link.resolve() == root / "usr/lib/hello/bin/hello"
    assert (root / "usr/lib/hello/data.txt").exists()


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-utils missing")
def test_desktop_file_is_valid(hello_spec, tmp_path):
    staging.build_stage(hello_spec, tmp_path)
    subprocess.run(["desktop-file-validate",
                    str(tmp_path / "usr/share/applications/org.example.Hello.desktop")], check=True)


def test_rpm_spec_lists_files(hello_spec, tmp_path):
    stage = tmp_path / "stage"
    staging.build_stage(hello_spec, stage)
    text = spec_file(BuildContext(hello_spec, stage, tmp_path, tmp_path, print))
    assert "Name: hello\n" in text and "BuildArch: noarch\n" in text
    assert "\n/usr/bin/hello\n" in text


@pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="dpkg-deb missing")
def test_build_deb_and_tarball(hello_spec):
    logs: list[str] = []
    result = core.build(hello_spec, log=logs.append)
    assert result.ok, result.errors
    deb = result.packages["deb"][0]
    assert deb.name == "hello_1.2.3_all.deb"
    info = subprocess.run(["dpkg-deb", "-f", str(deb)], capture_output=True, text=True, check=True).stdout
    assert "Package: hello" in info and "Maintainer: Test <test@example.org>" in info
    contents = subprocess.run(["dpkg-deb", "-c", str(deb)], capture_output=True, text=True, check=True).stdout
    assert "root/root" in contents and "./usr/bin/hello" in contents
    with tarfile.open(result.packages["tarball"][0]) as tar:
        assert "usr/bin/hello" in tar.getnames()


@pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="dpkg-deb missing")
def test_build_deb_with_strict_umask(hello_spec):
    old = os.umask(0o027)
    try:
        result = core.build(hello_spec, ["deb"], log=lambda _: None)
    finally:
        os.umask(old)
    assert result.ok, result.errors


def test_missing_tool_is_reported_not_raised(hello_spec, monkeypatch):
    from packagingonlinux.backends import BACKENDS
    monkeypatch.setattr(BACKENDS["rpm"], "required_tools", ("definitely-not-installed-tool",))
    result = core.build(hello_spec, ["rpm", "tarball"], log=lambda _: None)
    assert "rpm" in result.errors and "tarball" in result.packages


def test_build_command_gets_app_metadata(hello_spec):
    hello_spec.build_command = 'echo "$APP_ID $APP_NAME $APP_VERSION" > meta.txt'
    result = core.build(hello_spec, ["tarball"], log=lambda _: None)
    assert result.ok
    assert (hello_spec.base_dir / "meta.txt").read_text() == "org.example.Hello Hello 1.2.3\n"
