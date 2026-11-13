"""Flatpak: a single-file bundle (.flatpak) installable with `flatpak install --bundle`.

A manifest is generated with one "simple" module that copies the staging tree's usr/ into
/app. flatpak-builder builds it into a local OSTree repo, then `flatpak build-bundle`
exports the app from that repo. The runtime and SDK ([flatpak] runtime, by default the
freedesktop one) are installed for the user from Flathub on first use. The bundle refers
to Flathub so that installing it also pulls the runtime.

The app runs sandboxed: [flatpak] finish_args lists what it may access (by default the
display, the GPU and IPC, but not the user's files).
"""

from __future__ import annotations

import json
import platform
import shutil
from pathlib import Path

from packagingonlinux.backend import Backend, BuildContext
from packagingonlinux.config import AppSpec
from packagingonlinux.linux import staging
from packagingonlinux.runner import Log, run

FLATHUB_REPO = "https://dl.flathub.org/repo/flathub.flatpakrepo"

# rpm arch (from the ELF header) or `uname -m` -> Flatpak arch
_ARCHES = {"x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}


def flatpak_arch(spec: AppSpec, log: Log) -> str:
    rpm_arch = spec.linux_arch[1]
    if rpm_arch == "noarch":
        rpm_arch = platform.machine()
        log(f"the app is a script: building the Flatpak for this machine ({rpm_arch})")
    if rpm_arch not in _ARCHES:
        raise ValueError(f"Flatpak does not support the {rpm_arch} architecture (only x86_64 and aarch64)")
    return _ARCHES[rpm_arch]


def check(spec: AppSpec) -> None:
    """Raise ValueError for what Flatpak refuses but the other formats accept."""
    parts = spec.id.split(".")
    if any("-" in p for p in parts[:-1]):
        raise ValueError(f"Flatpak app id {spec.id!r}: only its last part may contain '-'")
    if spec.linux.icon:
        rel, _ = staging.icon_destination(spec)
        if rel.startswith("usr/share/pixmaps/"):
            raise ValueError("Flatpak needs a square icon of a standard size (or an SVG): "
                             "the current icon only fits /usr/share/pixmaps")


def manifest(spec: AppSpec, source: Path) -> dict:
    options = spec.flatpak
    return {
        "id": spec.id,
        "runtime": options.runtime,
        "runtime-version": options.runtime_version,
        "sdk": options.sdk_name,
        "command": spec.linux.exec_name,
        "finish-args": options.finish_args,
        "modules": [{
            "name": spec.package_name,
            "buildsystem": "simple",
            # Prebuilt binaries: leave them exactly as they are.
            "build-options": {"no-debuginfo": True, "strip": False},
            "sources": [{"type": "dir", "path": str(source)}],
            "build-commands": ["cp -a usr/. /app/"],
        }],
    }


class FlatpakBackend(Backend):
    name = "flatpak"
    label = "Flatpak (.flatpak)"
    required_tools = ("flatpak", "flatpak-builder")
    # librsvg2-common: flatpak-builder runs `appstreamcli compose`, which needs it to read SVG icons
    install_hint = "apt install flatpak flatpak-builder librsvg2-common  |  dnf install flatpak-builder"

    def build(self, ctx: BuildContext) -> list[Path]:
        spec = ctx.spec
        check(spec)
        arch = flatpak_arch(spec, ctx.log)
        source = ctx.workdir / "source"
        shutil.copytree(ctx.stage, source, symlinks=True)
        manifest_path = ctx.workdir / f"{spec.id}.json"
        manifest_path.write_text(json.dumps(manifest(spec, source), indent=2) + "\n", encoding="utf-8")

        repo = ctx.workdir / "repo"
        run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_REPO], ctx.log)
        run(["flatpak-builder", "--user", "--install-deps-from=flathub", "--disable-rofiles-fuse",
             "--force-clean", f"--state-dir={ctx.workdir / 'state'}", f"--repo={repo}", f"--arch={arch}",
             str(ctx.workdir / "build"), str(manifest_path)], ctx.log)

        out = ctx.outdir / f"{spec.file_stem}-{spec.version}-{arch}.flatpak"
        run(["flatpak", "build-bundle", f"--arch={arch}", f"--runtime-repo={FLATHUB_REPO}",
             str(repo), str(out), spec.id], ctx.log)
        return [out]
