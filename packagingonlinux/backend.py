from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from packagingonlinux.config import AppSpec
from packagingonlinux.runner import Log, which


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
    # Packages providing required_tools on Ubuntu/Debian and on Fedora, installed by the CI
    # workflow (.github/workflows/package.yml, ci/github/install-tools.sh) for the requested
    # formats, on the runner or in the project's build image.
    apt_packages: tuple[str, ...] = ()
    dnf_packages: tuple[str, ...] = ()

    def missing_tools(self) -> list[str]:
        return [t for t in self.required_tools if not which(t)]

    def build(self, ctx: BuildContext) -> list[Path]:
        raise NotImplementedError
