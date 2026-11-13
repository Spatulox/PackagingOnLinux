"""Running external tools from a Flatpak sandbox or a PyInstaller-frozen app."""

from __future__ import annotations

import sys
from pathlib import Path

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
