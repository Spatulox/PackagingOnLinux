from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from packagingonlinux.config import AppSpec
from packagingonlinux.runner import Log


@dataclass
class BuildContext:
    spec: AppSpec
    stage: Path      # staging tree of the backend's platform (read-only: copy before modifying)
    workdir: Path    # scratch directory private to this backend
    outdir: Path     # where finished packages go
    log: Log


class Backend:
    name: str = ""
    label: str = ""
    platform: str = "linux"   # which [linux]/[windows] target and staging tree it packages
    required_tools: tuple[str, ...] = ()
    install_hint: str = ""

    def missing_tools(self) -> list[str]:
        return [t for t in self.required_tools if shutil.which(t) is None]

    def build(self, ctx: BuildContext) -> list[Path]:
        raise NotImplementedError
