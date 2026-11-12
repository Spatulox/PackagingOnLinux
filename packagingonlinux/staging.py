"""Build the common FHS tree that every Linux backend packages.

Layout (single binary):
    usr/bin/<exec>
    usr/share/applications/<id>.desktop
    usr/share/icons/hicolor/<N>x<N>/apps/<id>.png   (or scalable/apps/<id>.svg, or pixmaps/<id>.png)
    usr/share/metainfo/<id>.metainfo.xml

Layout (directory app): files go to usr/lib/<package>/ and usr/bin/<exec> is a relative symlink.

Only freedesktop standards are used, so the result works on any desktop environment.
"""

from __future__ import annotations

import os
import shutil
import struct
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from packagingonlinux.config import AppSpec, ConfigError, Target

HICOLOR_SIZES = {16, 22, 24, 32, 48, 64, 96, 128, 256, 512}


def png_size(path: Path) -> tuple[int, int] | None:
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


def _linux(spec: AppSpec) -> Target:
    if spec.linux is None:
        raise ConfigError("no [linux] section in the config")
    return spec.linux


def icon_destination(spec: AppSpec) -> tuple[str, list[str]]:
    """Return (path relative to the stage root, warnings) for the app icon."""
    icon = _linux(spec).icon
    assert icon is not None
    suffix = icon.suffix.lower()
    if suffix == ".svg":
        return f"usr/share/icons/hicolor/scalable/apps/{spec.id}.svg", []
    size = png_size(icon) if suffix == ".png" else None
    if size is None:
        raise ValueError(f"icon must be a PNG or SVG file: {icon}")
    w, h = size
    if w == h and w in HICOLOR_SIZES:
        return f"usr/share/icons/hicolor/{w}x{w}/apps/{spec.id}.png", []
    warning = (
        f"icon is {w}x{h}: hicolor needs a square icon of size "
        f"{sorted(HICOLOR_SIZES)}; installing to /usr/share/pixmaps instead "
        "(fine for deb/rpm, required to fix for Flatpak/Snap store publishing)"
    )
    return f"usr/share/pixmaps/{spec.id}.png", [warning]


def desktop_entry(spec: AppSpec) -> str:
    target = _linux(spec)
    categories = ";".join(spec.categories) + ";"
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={spec.name}",
        f"Comment={spec.summary}",
        f"Exec={target.exec_name}",
        f"Categories={categories}",
        "Terminal=false",
    ]
    if target.icon:
        lines.insert(4, f"Icon={spec.id}")
    return "\n".join(lines) + "\n"


def metainfo(spec: AppSpec) -> str:
    paragraphs = [p.strip() for p in spec.description_text.split("\n\n") if p.strip()]
    desc = "\n".join(f"    <p>{escape(' '.join(p.split()))}</p>" for p in paragraphs)
    developer = spec.maintainer.split("<")[0].strip() or spec.name
    homepage = f'  <url type="homepage">{escape(spec.homepage)}</url>\n' if spec.homepage else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<component type="desktop-application">
  <id>{escape(spec.id)}</id>
  <metadata_license>CC0-1.0</metadata_license>
  <project_license>{escape(spec.license)}</project_license>
  <name>{escape(spec.name)}</name>
  <summary>{escape(spec.summary)}</summary>
  <developer id="{escape(spec.id.rsplit('.', 1)[0])}">
    <name>{escape(developer)}</name>
  </developer>
  <description>
{desc}
  </description>
  <launchable type="desktop-id">{escape(spec.id)}.desktop</launchable>
{homepage}  <content_rating type="oars-1.1" />
  <releases>
    <release version="{escape(spec.version)}" date="{date.today().isoformat()}" />
  </releases>
</component>
"""


def _write(path: Path, content: str, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def _normalize_permissions(root: Path) -> None:
    """Directories 755, executables 755, other files 644 (what distro packages expect)."""
    for dirpath, dirnames, filenames in os.walk(root):
        os.chmod(dirpath, 0o755)
        for name in filenames:
            p = Path(dirpath) / name
            if p.is_symlink():
                continue
            p.chmod(0o755 if os.access(p, os.X_OK) else 0o644)


def build_stage(spec: AppSpec, root: Path) -> list[str]:
    """Populate `root` with the installed file tree. Returns warnings."""
    warnings: list[str] = []
    target = _linux(spec)
    root.mkdir(parents=True, exist_ok=True)
    bindir = root / "usr/bin"
    bindir.mkdir(parents=True, exist_ok=True)

    if target.binary:
        dest = bindir / target.exec_name
        shutil.copy2(target.binary, dest)
        dest.chmod(0o755)
    else:
        assert target.dir is not None
        libdir = root / "usr/lib" / spec.package_name
        shutil.copytree(target.dir, libdir, symlinks=True)
        exe = libdir / target.exec
        exe.chmod(exe.stat().st_mode | 0o111)
        link = bindir / target.exec_name
        link.symlink_to(os.path.relpath(exe, bindir))

    _write(root / f"usr/share/applications/{spec.id}.desktop", desktop_entry(spec))
    _write(root / f"usr/share/metainfo/{spec.id}.metainfo.xml", metainfo(spec))

    if target.icon:
        rel, icon_warnings = icon_destination(spec)
        warnings += icon_warnings
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target.icon, dest)
    else:
        warnings.append("no icon set: the app will show a generic icon in menus")

    _normalize_permissions(root)
    return warnings


def installed_files(root: Path) -> list[str]:
    """Absolute install paths of every file/symlink in the stage (sorted)."""
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() or p.is_symlink():
            out.append("/" + p.relative_to(root).as_posix())
    return out


def installed_size_kib(root: Path) -> int:
    total = sum(p.lstat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    return max(1, (total + 1023) // 1024)
