"""Build the Linux formats in a Docker container (--container).

This is how Linux packages are built from Windows (where it is the default), and from a
Linux host that lacks some packaging tools. Only the Linux platform goes to the container:
its build command and its backends run there, on Linux. The Windows formats, and the
Windows build command, stay on the host.

The container runs this same tool (`python3 -m packagingonlinux build --no-container`),
from PackagingOnLinux's own sources mounted read-only, in an image that has every Linux
packaging tool but snapcraft. It is built once from DOCKERFILE and tagged with its hash.
The config is passed on standard input (`-c -`), so that an unsaved GUI form works too;
the config's folder is mounted as the working directory and the output folder as /out.
"""

from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import os
import re
import sys
from pathlib import Path

from packagingonlinux import config
from packagingonlinux.config import AppSpec, ConfigError
from packagingonlinux.runner import CommandError, Log, capture, in_flatpak, run, which

IMAGE_ENV = "PACKAGINGONLINUX_CONTAINER_IMAGE"   # use this image instead of building ours
CACHE_VOLUME = "packagingonlinux-cache"          # AppImage runtime, Flatpak runtimes and SDKs
SOURCES_DIR = "/opt/packagingonlinux"            # PYTHONPATH in the container
FROZEN_SOURCES = "packagingonlinux-src"          # where the PyInstaller bundles ship the sources

# Everything the Linux backends use, but snapcraft (only distributed as a snap). /cache
# is world-writable so that a non-root user can use the volume mounted there: Docker
# copies the folder's mode into a new volume.
DOCKERFILE = """\
FROM ubuntu:24.04
RUN apt-get update \\
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \\
      python3 dpkg-dev rpm squashfs-tools flatpak flatpak-builder librsvg2-common appstream \\
      desktop-file-utils ca-certificates \\
 && rm -rf /var/lib/apt/lists/* \\
 && mkdir -m 1777 /cache
"""

# Formats the container can't build: format -> why, and what to do instead.
UNSUPPORTED = {
    "snap": "snap can't be built in a container (snapcraft is only distributed as a snap): "
            "build it on Linux with snapcraft, or in CI",
}


class ContainerError(CommandError):
    """Docker is missing or not running, or the container can't be set up."""


def default_enabled() -> bool:
    """Whether builds use the container when neither --container nor --no-container is
    given: on Windows, where the Linux packaging tools don't exist."""
    return sys.platform == "win32"


def docker_status() -> tuple[bool, str]:
    """(True, server version) when Docker is usable, else (False, what to do)."""
    if not which("docker"):
        return False, ("Docker is needed to build the Linux formats in a container, and it is not "
                       "installed: install Docker Desktop (https://docs.docker.com/get-docker/), "
                       "or Docker Engine on Linux")
    proc = capture(["docker", "info", "--format", "{{.ServerVersion}}"])
    if proc.returncode != 0:
        return False, "Docker is installed but not running: start Docker Desktop (or the docker service) and try again"
    return True, proc.stdout.strip()


def docker_problem() -> str | None:
    ok, text = docker_status()
    return None if ok else text


def image_tag() -> str:
    return "packagingonlinux-builder:" + hashlib.sha256(DOCKERFILE.encode()).hexdigest()[:12]


def ensure_image(log: Log) -> str:
    """The image to run: $PACKAGINGONLINUX_CONTAINER_IMAGE, or ours, built if missing."""
    custom = os.environ.get(IMAGE_ENV, "").strip()
    if custom:
        return custom
    tag = image_tag()
    if capture(["docker", "image", "inspect", tag]).returncode != 0:
        log(f"== container image {tag} (first use only, takes a few minutes)")
        run(["docker", "build", "--tag", tag, "-"], log, input=DOCKERFILE)
    return tag


def sources_dir() -> Path:
    """The folder of PackagingOnLinux's `packagingonlinux` package, mounted in the container."""
    if in_flatpak() or os.environ.get("APPIMAGE"):
        # Docker can't see inside the sandbox or the AppImage's FUSE mount.
        raise ContainerError("--container is not available from the Flatpak or the AppImage of "
                             "PackagingOnLinux: use its deb, rpm, snap, Windows or pip version")
    if getattr(sys, "frozen", False):
        path = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / FROZEN_SOURCES
    else:
        path = Path(__file__).resolve().parent
    if not (path / "__main__.py").is_file():
        raise ContainerError(f"PackagingOnLinux's Python sources, needed by --container, are not in {path}")
    return path


def _mount(**fields: str) -> str:
    """A --mount value; fields holding a comma or a quote are CSV-quoted, as Docker expects."""
    out = io.StringIO()
    csv.writer(out, lineterminator="").writerow(f"{k}={v}" for k, v in fields.items())
    return out.getvalue()


def files_outside(spec: AppSpec) -> list[Path]:
    """The [linux] files that are not inside the config's folder, the only one mounted."""
    target = spec.linux
    if target is None:
        return []
    base = spec.base_dir.resolve()
    paths = [p for p in (target.binary, target.dir, target.icon, *target.man) if p is not None]
    return [p for p in paths if not Path(p).resolve().is_relative_to(base)]


def docker_argv(spec: AppSpec, formats: list[str], image: str, sources: Path) -> list[str]:
    """The `docker run` command that builds `formats` (Linux ones) for `spec`."""
    argv = [
        "docker", "run", "--rm", "--interactive",
        "--mount", _mount(type="bind", source=str(spec.base_dir.resolve()), target="/src"),
        "--workdir", "/src",
        "--mount", _mount(type="bind", source=str(spec.output_dir.resolve()), target="/out"),
        "--mount", _mount(type="bind", source=str(sources), target=f"{SOURCES_DIR}/packagingonlinux",
                          readonly="true"),
        "--mount", _mount(type="volume", source=CACHE_VOLUME, target="/cache"),
    ]
    env = {"HOME": "/tmp", "XDG_CACHE_HOME": "/cache", "XDG_DATA_HOME": "/cache/share",
           "PYTHONPATH": SOURCES_DIR, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
    for key, value in env.items():
        argv += ["--env", f"{key}={value}"]
    if hasattr(os, "getuid"):
        # Linux and macOS hosts: what the build writes in the project and the output folder
        # belongs to the user, not to root. (Docker Desktop on Windows maps it already.)
        argv += ["--user", f"{os.getuid()}:{os.getgid()}"]
    if "flatpak" in formats:
        argv.append("--privileged")  # flatpak-builder sandboxes the build with bubblewrap
    return argv + [image, "python3", "-m", "packagingonlinux", "build", "--config", "-",
                   "--format", ",".join(formats), "--output", "/out", "--no-container"]


# The summary that `packagingonlinux build` prints at the end (see cli.cmd_build).
_BUILT = re.compile(r"^\s*built\s+(\S+)\s+/out/(.+?)\s*$")
_FAILED = re.compile(r"^\s*failed\s+(\S+)\s+(.*?)\s*$")


def build_linux(spec: AppSpec, formats: list[str], log: Log) -> tuple[dict[str, list[Path]], dict[str, str]]:
    """Build the Linux `formats` in the container. Returns (packages, errors) per format,
    like BuildResult. Raises ConfigError or ContainerError when nothing can be built."""
    packages: dict[str, list[Path]] = {}
    errors: dict[str, str] = {}
    for name in formats:
        if name in UNSUPPORTED:
            errors[name] = UNSUPPORTED[name]
            log(f"[{name}] SKIPPED: {UNSUPPORTED[name]}")
    names = [f for f in formats if f not in UNSUPPORTED]
    if not names:
        return packages, errors
    if spec.linux is None:
        raise ConfigError("\n".join(spec.target_problems("linux")))
    outside = files_outside(spec)
    if outside:
        raise ConfigError(f"with --container, the [linux] files must be inside the config's folder "
                          f"({spec.base_dir.resolve()}), the only one the container sees: "
                          + ", ".join(str(p) for p in outside))
    sources = sources_dir()
    image = ensure_image(log)
    # The Windows section stays on the host: its paths may be anywhere.
    toml = config.to_toml(dataclasses.replace(spec, windows=None), spec.base_dir)

    def watch(line: str) -> None:
        log(line)
        if m := _BUILT.match(line):
            if m[1] in names:
                packages.setdefault(m[1], []).append(spec.output_dir / m[2])
        elif m := _FAILED.match(line):
            if m[1] in names:
                errors[m[1]] = m[2]

    log("== linux build in a container")
    try:
        run(docker_argv(spec, names, image, sources), watch, input=toml)
        failure = "the container reported no result for this format"
    except CommandError as e:
        failure = f"the container build failed, see the log ({e})"
    for name in names:
        if name not in packages and name not in errors:
            errors[name] = failure
    return packages, errors
