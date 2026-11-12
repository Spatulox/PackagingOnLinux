"""Run external commands while streaming their output to a log callback."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

Log = Callable[[str], None]


class CommandError(RuntimeError):
    pass


def run(
    cmd: list[str] | str, log: Log, cwd: Path | None = None, shell: bool = False,
    env: dict[str, str] | None = None,
) -> None:
    shown = cmd if isinstance(cmd, str) else " ".join(cmd)
    log(f"$ {shown}")
    proc = subprocess.Popen(
        cmd, cwd=cwd, shell=shell, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace",
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        log("  " + line.rstrip("\n"))
    if proc.wait() != 0:
        raise CommandError(f"command failed (exit {proc.returncode}): {shown}")
