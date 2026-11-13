"""Snap: a .snap installable with `snap install --dangerous` (or published to the Snap Store).

A snapcraft.yaml is generated with one `dump` part holding the staging tree, and one app
whose command is usr/bin/<exec>. It is written as JSON, which is valid YAML, so no YAML
library is needed. `snapcraft pack` builds it: in an LXD container by default, or
directly on the machine when SNAPCRAFT_BUILD_ENVIRONMENT=host (CI; needs root and an
Ubuntu release matching [snap] base).

[snap] confinement is "strict" by default: the app only gets the [snap] plugs (display,
GPU, network, home folder by default). "classic" gives it the same access as a deb, which
the Snap Store only accepts after a manual review.
"""

from __future__ import annotations

import json
import platform
import re
import shutil
from pathlib import Path

from packagingonlinux.backend import Backend, BuildContext
from packagingonlinux.config import AppSpec
from packagingonlinux.linux import staging
from packagingonlinux.runner import run

CONFINEMENTS = ("strict", "classic", "devmode")

# `uname -m` -> snap (Debian) arch
_HOST_ARCHES = {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf", "riscv64": "riscv64",
                "ppc64le": "ppc64el", "s390x": "s390x"}


def host_arch() -> str:
    machine = platform.machine()
    if machine not in _HOST_ARCHES:
        raise ValueError(f"snapcraft does not run on this machine's architecture ({machine})")
    return _HOST_ARCHES[machine]


def check(spec: AppSpec) -> None:
    """Raise ValueError for what the snap format refuses but the other formats accept."""
    name = spec.package_name
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) or not re.search(r"[a-z]", name) or len(name) > 40:
        raise ValueError(f"snap name {name!r} (from the app name) must be at most 40 characters among "
                         "a-z, 0-9 and single '-', with at least one letter")
    if len(spec.version) > 32 or spec.version[-1] in ".+~":
        raise ValueError(f"snap version {spec.version!r} must be at most 32 characters "
                         "and not end with '.', '+' or '~'")
    if len(spec.summary) > 78:
        raise ValueError(f"snap summary must be at most 78 characters (it has {len(spec.summary)})")
    if spec.snap.confinement not in CONFINEMENTS:
        raise ValueError(f"[snap] confinement must be one of {', '.join(CONFINEMENTS)}")


def point_icon_into_snap(spec: AppSpec, stage: Path) -> None:
    """Make the desktop file's Icon= a path inside the snap: snapd only exports icons it can
    find there, and snapcraft does not look icon names up in the hicolor theme."""
    if not spec.linux.icon:
        return
    rel, _ = staging.icon_destination(spec)
    desktop = stage / f"usr/share/applications/{spec.id}.desktop"
    lines = desktop.read_text(encoding="utf-8").splitlines(keepends=True)
    desktop.write_text("".join("Icon=${SNAP}/" + rel + "\n" if line.startswith("Icon=") else line
                               for line in lines), encoding="utf-8")


def snapcraft_yaml(spec: AppSpec, source: str = "stage") -> dict:
    options = spec.snap
    name = spec.package_name
    deb_arch = spec.linux_arch[0]
    build_for = "all" if deb_arch == "all" else deb_arch
    app: dict = {
        "command": f"usr/bin/{spec.linux.exec_name}",
        "desktop": f"usr/share/applications/{spec.id}.desktop",
        "common-id": spec.id,
    }
    if options.extensions:
        app["extensions"] = options.extensions
    if options.confinement != "classic":  # classic snaps have no interfaces
        app["plugs"] = options.plugs
    part: dict = {"plugin": "dump", "source": source}
    if options.stage_packages:
        part["stage-packages"] = options.stage_packages
    data = {
        "name": name,
        "title": spec.name,
        "version": spec.version,
        "summary": spec.summary,
        "description": spec.description_text,
        "license": spec.license,
        "base": options.base,
        "grade": options.grade or ("devel" if "~" in spec.version else "stable"),
        "confinement": options.confinement,
        "platforms": {build_for: {"build-on": [host_arch()], "build-for": [build_for]}},
        "parts": {name: part},
        "apps": {name: app},
    }
    if spec.homepage:
        data["website"] = spec.homepage
    email = re.search(r"<([^<>@\s]+@[^<>\s]+)>", spec.maintainer)
    if email:
        data["contact"] = email.group(1)
    return data


class SnapBackend(Backend):
    name = "snap"
    label = "Snap (.snap)"
    required_tools = ("snapcraft",)
    install_hint = "snap install snapcraft --classic"

    def build(self, ctx: BuildContext) -> list[Path]:
        spec = ctx.spec
        check(spec)
        project = ctx.workdir / "project"
        shutil.copytree(ctx.stage, project / "stage", symlinks=True)
        point_icon_into_snap(spec, project / "stage")
        data = snapcraft_yaml(spec)
        (project / "snapcraft.yaml").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        arch = next(iter(data["platforms"]))
        filename = f"{spec.package_name}_{spec.version}_{arch}.snap"
        # snapcraft refuses to write the snap outside the project tree
        run(["snapcraft", "pack", "--output", filename], ctx.log, cwd=project)
        out = ctx.outdir / filename
        shutil.move(project / filename, out)
        return [out]
