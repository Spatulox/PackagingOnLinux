"""Build the Windows staging tree: the files installed in the app folder, flat.

Layout:
    <exe or the whole [windows] dir>
    <package_name>.ico        (when an icon is available, for shortcuts and the installer)

Symlinks are resolved: neither zip archives for Windows nor NSIS keep them.
"""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from packagingonlinux import ico, pe
from packagingonlinux.config import AppSpec, ConfigError, Target


def _windows(spec: AppSpec) -> Target:
    if spec.windows is None:
        raise ConfigError("no [windows] section in the config")
    return spec.windows


def exe_path(spec: AppSpec) -> str:
    """Path of the main executable inside the stage (POSIX separators)."""
    target = _windows(spec)
    return str(PurePosixPath(target.exec)) if target.dir else target.exec_name


def icon_name(spec: AppSpec) -> str:
    return f"{spec.package_name}.ico"


def icon_source(spec: AppSpec) -> Path | None:
    """[windows] icon, else the Linux icon (if it can be converted)."""
    target = _windows(spec)
    if target.icon:
        return target.icon
    return spec.linux.icon if spec.linux else None


def build_stage(spec: AppSpec, root: Path) -> list[str]:
    """Populate `root` with the files to install. Returns warnings."""
    target = _windows(spec)
    root.mkdir(parents=True, exist_ok=True)
    if target.binary:
        shutil.copy2(target.binary, root / target.binary.name)
    else:
        assert target.dir is not None
        shutil.copytree(target.dir, root, symlinks=False, dirs_exist_ok=True)
    exe = root / exe_path(spec)
    pe.detect_arch(exe)  # raises ValueError if it isn't a Windows executable

    warnings: list[str] = []
    source = icon_source(spec)
    if source is None:
        warnings.append("no icon set: Windows shortcuts will use the executable's own icon")
    elif (root / icon_name(spec)).exists():
        warnings.append(f"{icon_name(spec)} already exists in the app folder: used as the icon")
    else:
        warnings += ico.make_ico(source, root / icon_name(spec))
    return warnings


def installed_files(root: Path) -> list[str]:
    """Relative POSIX paths of every file in the stage (sorted)."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def installed_size_kib(root: Path) -> int:
    total = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
    return max(1, (total + 1023) // 1024)
