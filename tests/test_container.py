"""--container: the Linux formats built in a Docker container (the default on Windows)."""

from __future__ import annotations

import dataclasses
import io
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from packagingonlinux import cli, config, container, core, runner
from packagingonlinux.runner import CommandError
from tests.conftest import make_pe


def test_default_is_container_on_windows_only(monkeypatch):
    monkeypatch.setattr(container.sys, "platform", "win32")
    assert container.default_enabled()
    monkeypatch.setattr(container.sys, "platform", "linux")
    assert not container.default_enabled()


def test_docker_missing_or_stopped(monkeypatch):
    monkeypatch.setattr(container, "which", lambda tool: False)
    assert "not installed" in container.docker_problem()
    assert "Docker Desktop" in container.docker_problem()

    monkeypatch.setattr(container, "which", lambda tool: True)
    monkeypatch.setattr(container, "capture", lambda cmd: subprocess.CompletedProcess(cmd, 1, "", "no daemon"))
    assert "not running" in container.docker_problem()

    monkeypatch.setattr(container, "capture", lambda cmd: subprocess.CompletedProcess(cmd, 0, "29.1.1\n", ""))
    assert container.docker_problem() is None
    assert container.docker_status() == (True, "29.1.1")


def test_build_without_docker_fails_before_building_anything(hello_spec, monkeypatch):
    monkeypatch.setattr(container, "docker_problem", lambda: "Docker is installed but not running")
    hello_spec.linux.command = "touch ran"
    with pytest.raises(container.ContainerError, match="not running"):
        core.build(hello_spec, ["deb"], log=lambda m: None, container=True)
    assert not (hello_spec.base_dir / "ran").exists()
    assert not hello_spec.output_dir.exists()


def test_container_is_the_default_on_windows(hello_spec, monkeypatch):
    monkeypatch.setattr(container, "default_enabled", lambda: True)
    monkeypatch.setattr(container, "docker_problem", lambda: "Docker is needed ... not installed")
    with pytest.raises(container.ContainerError):
        core.build(hello_spec, ["deb"], log=lambda m: None)


def test_windows_formats_dont_need_docker(hello_spec, tmp_path, monkeypatch):
    hello_spec.windows = config.Target(binary=make_pe(tmp_path / "hello.exe"))
    monkeypatch.setattr(container, "docker_problem", lambda: pytest.fail("Docker checked"))
    result = core.build(hello_spec, ["zip"], log=lambda m: None, container=True)
    assert result.ok and result.packages["zip"]


def test_linux_formats_need_a_linux_host_without_container(hello_spec, monkeypatch):
    monkeypatch.setattr(core, "linux_host", lambda: False)
    result = core.build(hello_spec, ["deb", "tarball"], log=lambda m: None, container=False)
    assert result.packages == {}
    assert result.errors == {"deb": core.NOT_LINUX_HOST, "tarball": core.NOT_LINUX_HOST}
    status = {s.name: s for s in core.doctor()}
    assert status["deb"].missing == ["a Linux host"] and "--container" in status["deb"].install_hint
    assert status["zip"].ok


def test_docker_argv(hello_spec, tmp_path):
    sources = tmp_path / "src dir,with comma"
    argv = container.docker_argv(hello_spec, ["deb", "tarball"], "img:1", sources)
    assert argv[:4] == ["docker", "run", "--rm", "--interactive"]
    mounts = [argv[i + 1] for i, a in enumerate(argv) if a == "--mount"]
    assert mounts == [
        f"type=bind,source={hello_spec.base_dir.resolve()},target=/src",
        f"type=bind,source={hello_spec.output_dir.resolve()},target=/out",
        f'type=bind,"source={sources}",target=/opt/packagingonlinux/packagingonlinux,readonly=true',
        "type=volume,source=packagingonlinux-cache,target=/cache",
    ]
    assert argv[argv.index("--workdir") + 1] == "/src"
    assert "PYTHONPATH=/opt/packagingonlinux" in argv
    assert argv[argv.index("img:1"):] == [
        "img:1", "python3", "-m", "packagingonlinux", "build", "--config", "-",
        "--format", "deb,tarball", "--output", "/out", "--no-container"]
    assert "--privileged" not in argv
    if hasattr(os, "getuid"):
        assert argv[argv.index("--user") + 1] == f"{os.getuid()}:{os.getgid()}"
    assert "--privileged" in container.docker_argv(hello_spec, ["flatpak"], "img:1", sources)


def _fake_container(monkeypatch, tmp_path, lines: list[str], exit_code: int = 0) -> list:
    calls = []

    def fake_run(cmd, log, cwd=None, shell=False, env=None, input=None):
        calls.append((cmd, input))
        for line in lines:
            log("  " + line)
        if exit_code:
            raise CommandError(f"command failed (exit {exit_code}): docker run")

    monkeypatch.setattr(container, "run", fake_run)
    monkeypatch.setattr(container, "ensure_image", lambda log: "img:1")
    monkeypatch.setattr(container, "sources_dir", lambda: tmp_path)
    return calls


def test_build_linux_maps_results_to_the_host(hello_spec, tmp_path, monkeypatch):
    hello_spec.windows = config.Target(binary=Path("/elsewhere/hello.exe"))  # outside: never mounted
    calls = _fake_container(monkeypatch, tmp_path, [
        "== deb", "[deb] OK /out/hello_1.2.3_all.deb", "",
        "built   deb      /out/hello_1.2.3_all.deb",
        "failed  rpm      rpmbuild: bad spec",
    ], exit_code=1)
    log: list[str] = []
    packages, errors = container.build_linux(hello_spec, ["deb", "rpm", "appimage", "snap"], log.append)
    assert packages == {"deb": [hello_spec.output_dir / "hello_1.2.3_all.deb"]}
    assert errors["rpm"] == "rpmbuild: bad spec"
    assert "container build failed" in errors["appimage"]
    assert errors["snap"] == container.UNSUPPORTED["snap"]
    (argv, toml), = calls
    assert "--format" in argv and argv[argv.index("--format") + 1] == "deb,rpm,appimage"
    # The config goes on stdin, without the Windows section, with paths relative to /src.
    assert "[windows]" not in toml and 'binary = "hello"' in toml
    assert config.from_dict(tomllib.loads(toml), Path("/src")).linux.binary == Path("/src/hello")
    assert "  built   deb      /out/hello_1.2.3_all.deb" in log


def test_build_linux_only_snap_runs_nothing(hello_spec, tmp_path, monkeypatch):
    calls = _fake_container(monkeypatch, tmp_path, [])
    packages, errors = container.build_linux(hello_spec, ["snap"], lambda m: None)
    assert calls == [] and packages == {} and list(errors) == ["snap"]


def test_files_outside_the_config_folder_are_refused(hello_spec, tmp_path, monkeypatch):
    calls = _fake_container(monkeypatch, tmp_path, [])
    hello_spec.linux = dataclasses.replace(hello_spec.linux, icon=tmp_path.parent / "icon.png")
    with pytest.raises(config.ConfigError, match="inside the config's folder"):
        container.build_linux(hello_spec, ["deb"], lambda m: None)
    assert calls == []
    # core.build reports it per format instead.
    monkeypatch.setattr(container, "docker_problem", lambda: None)
    result = core.build(hello_spec, ["deb", "tarball"], log=lambda m: None, container=True)
    assert set(result.errors) == {"deb", "tarball"}


def test_sources_dir():
    assert (container.sources_dir() / "container.py").is_file()


def test_sources_dir_refused_from_an_appimage(monkeypatch):
    monkeypatch.setenv("APPIMAGE", "/home/me/PackagingOnLinux.AppImage")
    with pytest.raises(container.ContainerError, match="AppImage"):
        container.sources_dir()


def test_config_from_stdin(hello_project, monkeypatch):
    monkeypatch.chdir(hello_project.parent)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(hello_project.read_bytes())))
    spec = config.load(Path("-"))
    assert spec.base_dir == hello_project.parent
    assert spec.linux.binary == hello_project.parent / "hello"


@pytest.mark.skipif(not shutil.which("cat"), reason="needs cat")
def test_run_writes_input():
    log: list[str] = []
    runner.run(["cat"], log.append, input="line 1\nline 2\n")
    assert log[1:] == ["  line 1", "  line 2"]


@pytest.mark.parametrize("args, expected", [([], None), (["--container"], True), (["--no-container"], False)])
def test_cli_passes_container_option(hello_project, monkeypatch, args, expected):
    seen = {}

    def fake_build(spec, formats, container=None):
        seen["container"] = container
        return core.BuildResult()

    monkeypatch.setattr(core, "build", fake_build)
    assert cli.main(["build", "-c", str(hello_project), *args]) == 0
    assert seen == {"container": expected}


def test_cli_reports_missing_docker(hello_project, monkeypatch, capsys):
    monkeypatch.setattr(container, "docker_problem", lambda: "Docker is installed but not running: start it")
    assert cli.main(["build", "-c", str(hello_project), "-f", "deb", "--container"]) == 2
    assert "error: Docker is installed but not running" in capsys.readouterr().err


def _docker_running() -> bool:
    return shutil.which("docker") is not None and container.docker_problem() is None


@pytest.mark.skipif(os.environ.get("PACKAGINGONLINUX_TEST_CONTAINER") != "1" or not _docker_running(),
                    reason="set PACKAGINGONLINUX_TEST_CONTAINER=1, with Docker running (slow: builds the image)")
def test_real_container_build(hello_spec):
    result = core.build(hello_spec, ["deb", "rpm", "tarball"], log=print, container=True)
    assert result.ok, result.errors
    for name in ("deb", "rpm", "tarball"):
        (path,) = result.packages[name]
        assert path.is_file() and path.parent == hello_spec.output_dir
        if hasattr(os, "getuid"):
            assert path.stat().st_uid == os.getuid()
