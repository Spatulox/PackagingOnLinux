"""AppImage: one executable file that runs on any distribution, without installation.

An AppImage is the AppImage runtime (a small static ELF) followed by a squashfs image of
an AppDir. The AppDir is the staging tree plus the files the runtime and desktop
integration tools look for at its root:

    AppRun -> usr/bin/<exec>      what the runtime starts
    <id>.desktop                  copy of usr/share/applications/<id>.desktop
    <id>.png | <id>.svg           the icon named by the desktop file's Icon= key
    .DirIcon -> <id>.png          icon shown by file managers

The image is made with mksquashfs and the runtime is downloaded once (pinned release,
checked against its sha256) into the user's cache, so neither appimagetool nor FUSE is
needed to build. The app's libraries are not bundled: the AppImage runs with the host's
libraries, like the tar.gz.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import urllib.request
from pathlib import Path

from packagingonlinux.backend import Backend, BuildContext
from packagingonlinux.config import AppSpec
from packagingonlinux.linux import staging
from packagingonlinux.runner import Log, run

RUNTIME_ENV = "PACKAGINGONLINUX_APPIMAGE_RUNTIME"
RUNTIME_RELEASE = "20251108"
RUNTIME_URL = "https://github.com/AppImage/type2-runtime/releases/download/{release}/runtime-{arch}"
RUNTIME_SHA256 = {
    "x86_64": "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
    "aarch64": "00cbdfcf917cc6c0ff6d3347d59e0ca1f7f45a6df1a428a0d6d8a78664d87444",
    "armhf": "e9060d37577b8a29914ec12d8740add24e19ff29012fb1fa0f60daf62db0688d",
    "i686": "e72ea0b140a0a16e680713238a6f30aad278b62c4ca17919c554864124515498",
}

# rpm arch (from the ELF header) or `uname -m` -> AppImage arch
_ARCHES = {
    "x86_64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64",
    "armv7hl": "armhf", "armv7l": "armhf", "i686": "i686", "i386": "i686",
}


def appimage_arch(spec: AppSpec, log: Log) -> str:
    """The AppImage architecture of the app; scripts get the build machine's."""
    rpm_arch = spec.linux_arch[1]
    if rpm_arch == "noarch":
        host = platform.machine()
        if host not in _ARCHES:
            raise ValueError(f"no AppImage runtime for this machine's architecture ({host})")
        log(f"warning: the app is a script, so the AppImage is built for this machine ({_ARCHES[host]}) "
            "and runs the script with the interpreter installed on the user's system")
        return _ARCHES[host]
    if rpm_arch not in _ARCHES:
        raise ValueError(f"AppImage does not support the {rpm_arch} architecture")
    return _ARCHES[rpm_arch]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "packagingonlinux"


def runtime(arch: str, log: Log) -> Path:
    """Path of the AppImage runtime for `arch`: $PACKAGINGONLINUX_APPIMAGE_RUNTIME if set,
    otherwise the pinned release, downloaded into the cache on first use."""
    override = os.environ.get(RUNTIME_ENV)
    if override:
        path = Path(override)
        if not path.is_file():
            raise ValueError(f"{RUNTIME_ENV}={override}: file not found")
        return path
    expected = RUNTIME_SHA256[arch]
    path = cache_dir() / f"appimage-runtime-{RUNTIME_RELEASE}-{arch}"
    if path.is_file() and _sha256(path) == expected:
        return path
    url = RUNTIME_URL.format(release=RUNTIME_RELEASE, arch=arch)
    log(f"downloading the AppImage runtime: {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as response, open(partial, "wb") as f:
            shutil.copyfileobj(response, f)
    except OSError as e:
        partial.unlink(missing_ok=True)
        raise OSError(f"cannot download the AppImage runtime ({e}). Download {url} yourself "
                      f"and set {RUNTIME_ENV} to its path.") from None
    actual = _sha256(partial)
    if actual != expected:
        partial.unlink()
        raise ValueError(f"the AppImage runtime downloaded from {url} has sha256 {actual}, "
                         f"expected {expected}")
    partial.replace(path)
    return path


def make_appdir(ctx: BuildContext, appdir: Path) -> None:
    """Copy the stage into `appdir` and add AppRun, the root .desktop file and icon."""
    spec = ctx.spec
    shutil.copytree(ctx.stage, appdir, symlinks=True)
    (appdir / "AppRun").symlink_to(f"usr/bin/{spec.linux.exec_name}")
    shutil.copyfile(appdir / f"usr/share/applications/{spec.id}.desktop", appdir / f"{spec.id}.desktop")
    if spec.linux.icon:
        rel, _ = staging.icon_destination(spec)
        icon = f"{spec.id}{Path(rel).suffix}"
        shutil.copyfile(appdir / rel, appdir / icon)
        (appdir / ".DirIcon").symlink_to(icon)


class AppImageBackend(Backend):
    name = "appimage"
    label = "AppImage (.AppImage)"
    required_tools = ("mksquashfs",)
    install_hint = "apt install squashfs-tools  |  dnf install squashfs-tools"

    def build(self, ctx: BuildContext) -> list[Path]:
        spec = ctx.spec
        arch = appimage_arch(spec, ctx.log)
        runtime_file = runtime(arch, ctx.log)
        appdir = ctx.workdir / "AppDir"
        make_appdir(ctx, appdir)

        image = ctx.workdir / "image.squashfs"
        run(["mksquashfs", str(appdir), str(image), "-all-root", "-noappend", "-no-xattrs",
             "-comp", "zstd", "-quiet"], ctx.log)

        out = ctx.outdir / f"{spec.file_stem}-{spec.version}-{arch}.AppImage"
        with open(out, "wb") as f:
            for part in (runtime_file, image):
                with open(part, "rb") as src:
                    shutil.copyfileobj(src, f)
        out.chmod(0o755)
        return [out]
