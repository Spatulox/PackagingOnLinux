"""Run external commands while streaming their output to a log callback.

Every external tool (dpkg-deb, rpmbuild, the user's build command...) goes through this
module, so that it also runs when PackagingOnLinux itself is packaged:

- in a Flatpak, the sandbox has none of these tools: commands run on the host through
  `flatpak-spawn --host` (needs --talk-name=org.freedesktop.Flatpak), and temporary
  directories go to a folder the host sees at the same path;
- frozen by PyInstaller, the app sets LD_LIBRARY_PATH to its bundled libraries, which the
  host's tools must not load: it is restored for them.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]

FLATPAK_INFO = Path("/.flatpak-info")


class CommandError(RuntimeError):
    pass


def in_flatpak() -> bool:
    return FLATPAK_INFO.exists()


def tool_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """The environment for an external tool: `env` (default: ours) without what a
    PyInstaller-frozen app adds to it."""
    env = dict(os.environ if env is None else env)
    if getattr(sys, "frozen", False):
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def host_argv(cmd: list[str] | str, cwd: Path | None = None, shell: bool = False,
              env: dict[str, str] | None = None) -> list[str]:
    """`cmd` wrapped in flatpak-spawn --host. Only the variables that `env` adds or changes
    are passed on: the host keeps its own environment."""
    argv = ["flatpak-spawn", "--host", f"--directory={cwd or Path.cwd()}"]
    for key, value in (env or {}).items():
        if os.environ.get(key) != value:
            argv.append(f"--env={key}={value}")
    if shell:
        assert isinstance(cmd, str)
        return argv + ["sh", "-c", cmd]
    return argv + list(cmd)


def _popen_args(cmd: list[str] | str, cwd: Path | None, shell: bool,
                env: dict[str, str] | None) -> tuple[list[str] | str, dict]:
    if in_flatpak():
        return host_argv(cmd, cwd, shell, env), {"env": tool_env()}
    return cmd, {"cwd": cwd, "shell": shell, "env": tool_env(env)}


def run(
    cmd: list[str] | str, log: Log, cwd: Path | None = None, shell: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    log(f"$ {shown}")
    argv, kwargs = _popen_args(cmd, cwd, shell, env)
    proc = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", **kwargs,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log("  " + line.rstrip("\n"))
    if proc.wait() != 0:
        raise CommandError(f"command failed (exit {proc.returncode}): {shown}")


def capture(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run `cmd` and return its result, with stdout and stderr captured as text."""
    argv, kwargs = _popen_args(cmd, cwd, False, None)
    return subprocess.run(argv, capture_output=True, text=True, errors="replace", **kwargs)


@functools.cache
def _host_has(tool: str) -> bool:
    return capture(["sh", "-c", 'command -v "$1"', "sh", tool]).returncode == 0


def which(tool: str) -> bool:
    """Whether `tool` is installed where commands run (the host, from a Flatpak)."""
    if in_flatpak():
        return _host_has(tool)
    return shutil.which(tool) is not None


def work_root() -> Path | None:
    """Parent of temporary directories (None: the system default). In a Flatpak, /tmp is
    private to the sandbox, so they go to the app's cache folder, which the host sees at
    the same path (~/.var/app/<id>/cache)."""
    if not in_flatpak():
        return None
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "packagingonlinux/tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root


def temp_dir(prefix: str = "packagingonlinux-") -> tempfile.TemporaryDirectory[str]:
    """A temporary directory that external tools can also read and write."""
    return tempfile.TemporaryDirectory(prefix=prefix, dir=work_root())
