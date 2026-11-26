"""Run external commands while streaming their output to a log callback.

Every external tool (dpkg-deb, rpmbuild, the user's build command...) goes through this
module, so that it also runs when PackagingOnLinux itself is packaged:

- in a Flatpak, the sandbox has none of these tools: commands run on the host through
  `flatpak-spawn --host` (needs --talk-name=org.freedesktop.Flatpak), and temporary
  directories go to a folder the host sees at the same path;
- frozen by PyInstaller, the app sets LD_LIBRARY_PATH to its bundled libraries, which the
  host's tools must not load: it is restored for them;
- started from the desktop menu, the app has the session's environment, without what the
  user's shell startup files add (e.g. ~/go/bin or nvm in PATH): `load_login_env` reads it
  from their login shell, like editors do.
"""

from __future__ import annotations

import functools
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]

FLATPAK_INFO = Path("/.flatpak-info")

# Variables of the login shell's environment that are not taken: the shell's own state, and
# the library path that tool_env manages for a PyInstaller-frozen app.
LOGIN_ENV_SKIPPED = frozenset({"_", "PWD", "OLDPWD", "SHLVL", "LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG"})
_ENV_MARKER = "__PACKAGINGONLINUX_ENV__"
# From a Flatpak: the host login shell's environment, given to every command run on the host
# (the sandbox's os.environ is not the host's, so it is kept apart).
_host_env: dict[str, str] = {}


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
    """`cmd` wrapped in flatpak-spawn --host. Only the variables that the login shell's
    environment (see load_login_env) and `env` add or change are passed on: the host keeps
    its own environment."""
    argv = ["flatpak-spawn", "--host", f"--directory={cwd or Path.cwd()}"]
    passed = {key: value for key, value in _host_env.items() if os.environ.get(key) != value}
    passed.update((key, value) for key, value in (env or {}).items() if os.environ.get(key) != value)
    for key, value in passed.items():
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


def login_shell() -> str:
    """The user's shell: $SHELL, else their passwd entry."""
    shell = os.environ.get("SHELL")
    if shell:
        return shell
    try:
        return pwd.getpwuid(os.getuid()).pw_shell or "/bin/sh"
    except KeyError:
        return "/bin/sh"


def parse_env_dump(output: str) -> dict[str, str]:
    """The variables of `env -0` printed between two markers, ignoring what the shell's
    startup files print around it."""
    start = output.find(_ENV_MARKER + "\n")
    end = output.rfind(_ENV_MARKER)
    if start < 0 or end <= start:
        return {}
    env = {}
    for entry in output[start + len(_ENV_MARKER) + 1:end].split("\0"):
        key, eq, value = entry.partition("=")
        if eq and key and key not in LOGIN_ENV_SKIPPED:
            env[key] = value
    return env


def login_env(timeout: float = 10) -> dict[str, str]:
    """The environment of the user's interactive login shell (`$SHELL -ilc`), which reads
    their startup files (~/.profile, ~/.bashrc, ~/.zshrc...). On the host from a Flatpak."""
    shell = login_shell()
    cmd = [shell, "-ilc", f"echo {_ENV_MARKER}; env -0; echo {_ENV_MARKER}"]
    argv, kwargs = _popen_args(cmd, None, False, None)
    try:
        # A new session: the interactive shell has no terminal to take over.
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              errors="replace", timeout=timeout, start_new_session=True, **kwargs)
    except subprocess.TimeoutExpired:
        raise CommandError(f"{shell} took more than {timeout:g}s to start") from None
    except OSError as e:
        raise CommandError(f"cannot run {shell}: {e}") from None
    env = parse_env_dump(proc.stdout)
    if not env:
        raise CommandError(f"no environment read from {shell} (exit {proc.returncode})")
    return env


def load_login_env(timeout: float = 10) -> str:
    """Make external tools run with the user's login shell environment, e.g. for an app
    started from the desktop menu. Returns the shell; raises CommandError on failure."""
    env = login_env(timeout)
    if in_flatpak():
        _host_env.clear()
        _host_env.update(env)
        _host_has.cache_clear()
    else:
        os.environ.update(env)
    return login_shell()


def started_from_terminal() -> bool:
    """Whether the app was started from a terminal, whose environment already has what the
    user's shell startup files set."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (OSError, ValueError):
        return False
