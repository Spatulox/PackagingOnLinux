"""Running external tools from a Flatpak sandbox or a PyInstaller-frozen app."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from packagingonlinux import runner


def test_host_argv_wraps_command(monkeypatch):
    monkeypatch.setenv("KEPT", "same")
    argv = runner.host_argv(["dpkg-deb", "--build", "x"], cwd=Path("/home/me/proj"),
                            env={"KEPT": "same", "APP_ID": "org.example.Hello"})
    assert argv == ["flatpak-spawn", "--host", "--directory=/home/me/proj",
                    "--env=APP_ID=org.example.Hello", "dpkg-deb", "--build", "x"]
    assert runner.host_argv("make && make install", Path("/p"), shell=True)[-3:] == [
        "sh", "-c", "make && make install"]


def test_run_goes_through_flatpak_spawn(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, argv, **kwargs):
            calls.append((argv, kwargs))
            self.stdout = iter(["hi\n"])

        def wait(self):
            return 0

    monkeypatch.setattr(runner, "in_flatpak", lambda: True)
    monkeypatch.setattr(runner.subprocess, "Popen", FakePopen)
    logs: list[str] = []
    runner.run("echo hi", logs.append, cwd=Path("/p"), shell=True)
    argv, kwargs = calls[0]
    assert argv[:3] == ["flatpak-spawn", "--host", "--directory=/p"] and argv[-3:] == ["sh", "-c", "echo hi"]
    assert "shell" not in kwargs and "cwd" not in kwargs
    assert logs == ["$ echo hi", "  hi"]


def test_temp_dirs_are_visible_from_the_host_in_flatpak(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "in_flatpak", lambda: True)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with runner.temp_dir() as tmp:
        assert Path(tmp).parent == tmp_path / "packagingonlinux/tmp"


def test_frozen_app_restores_library_path(monkeypatch):
    env = {"LD_LIBRARY_PATH": "/bundle/_internal", "LD_LIBRARY_PATH_ORIG": "/opt/lib", "PATH": "/usr/bin"}
    assert runner.tool_env(env) == env  # not frozen: unchanged
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert runner.tool_env(env) == {"LD_LIBRARY_PATH": "/opt/lib", "PATH": "/usr/bin"}
    assert runner.tool_env({"LD_LIBRARY_PATH": "/bundle/_internal"}) == {}


def fake_shell(tmp_path, body: str) -> Path:
    """A $SHELL that runs `body`, then its -c command with sh."""
    shell = tmp_path / "fakeshell"
    shell.write_text(f'#!/bin/sh\n{body}\nexec sh -c "$2"\n')
    shell.chmod(0o755)
    return shell


def test_parse_env_dump_ignores_startup_output():
    m = runner._ENV_MARKER
    out = f"Welcome!\n{m}\nFOO=a=b\0MULTI=1\n2\0PWD=/x\0SHLVL=2\0{m}\nbye\n"
    assert runner.parse_env_dump(out) == {"FOO": "a=b", "MULTI": "1\n2"}
    assert runner.parse_env_dump("no marker") == {}


def test_load_login_env_takes_shell_startup_files(tmp_path, monkeypatch):
    tools = tmp_path / "go-bin"
    tools.mkdir()
    (tools / "pol-test-tool").write_text("#!/bin/sh\n")
    (tools / "pol-test-tool").chmod(0o755)
    shell = fake_shell(tmp_path, f'echo "startup noise"\nexport PATH="$PATH:{tools}" GOPATH=/gopath')
    monkeypatch.setenv("SHELL", str(shell))
    monkeypatch.setenv("PATH", os.environ["PATH"])  # restored after the test
    monkeypatch.delenv("GOPATH", raising=False)
    assert not runner.which("pol-test-tool")
    assert runner.load_login_env() == str(shell)
    assert os.environ["GOPATH"] == "/gopath"
    assert runner.which("pol-test-tool")
    monkeypatch.delenv("GOPATH")


def test_login_env_failures(tmp_path, monkeypatch):
    monkeypatch.setenv("SHELL", str(fake_shell(tmp_path, "exit 3")))
    with pytest.raises(runner.CommandError, match="exit 3"):
        runner.login_env()
    monkeypatch.setenv("SHELL", str(fake_shell(tmp_path, "sleep 5")))
    with pytest.raises(runner.CommandError, match="took more than"):
        runner.login_env(timeout=0.3)
    monkeypatch.setenv("SHELL", str(tmp_path / "missing"))
    with pytest.raises(runner.CommandError, match="cannot run"):
        runner.login_env()


def test_flatpak_host_commands_get_login_env(monkeypatch):
    monkeypatch.setenv("HOME", "/home/me")
    monkeypatch.setattr(runner, "_host_env", {"PATH": "/usr/bin:/home/me/go/bin", "HOME": "/home/me"})
    argv = runner.host_argv(["wails", "build"], cwd=Path("/p"), env={**os.environ, "APP_ID": "org.example.Hello"})
    assert argv == ["flatpak-spawn", "--host", "--directory=/p", "--env=PATH=/usr/bin:/home/me/go/bin",
                    "--env=APP_ID=org.example.Hello", "wails", "build"]
