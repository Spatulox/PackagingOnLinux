"""packaging.toml <-> AppSpec.

The TOML file is the exchange format between the GUI, the CLI and CI. Relative paths in
it are resolved against the directory that contains the file.

Schema:
    [app]     id, name, version, summary, description, license, maintainer, homepage, categories
    [linux]   command, binary | dir (+ exec), icon
    [windows] command, binary | dir (+ exec), icon      (optional, same keys)
    [deps]    auto, deb, rpm        (optional, Linux only)
    [output]  formats, dir

Each platform's `command` is optional and runs before packaging, only when a format of that
platform is built, with $APP_ID, $APP_NAME, $APP_VERSION and $APP_PLATFORM set.

The older layout ([files] + [build] command) is still read as [linux].
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from packagingonlinux import elf, pe

CONFIG_NAME = "packaging.toml"

PLATFORMS = ("linux", "windows")

# Main categories from the freedesktop menu spec.
MAIN_CATEGORIES = [
    "AudioVideo", "Audio", "Video", "Development", "Education", "Game", "Graphics",
    "Network", "Office", "Science", "Settings", "System", "Utility",
]

# Common SPDX license ids, offered as choices in the GUI (any SPDX expression is accepted).
COMMON_LICENSES = [
    "LicenseRef-proprietary", "MIT", "Apache-2.0", "GPL-3.0-only", "GPL-3.0-or-later",
    "GPL-2.0-only", "GPL-2.0-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later", "LGPL-2.1-only",
    "LGPL-2.1-or-later", "AGPL-3.0-only", "AGPL-3.0-or-later", "MPL-2.0", "BSD-3-Clause",
    "BSD-2-Clause", "ISC", "Zlib", "EPL-2.0", "Unlicense", "CC0-1.0",
]


class ConfigError(ValueError):
    pass


@dataclass
class Target:
    """What to package for one platform: a single executable or a directory, plus an icon,
    and the optional command that produces them."""

    binary: Path | None = None
    dir: Path | None = None
    exec: str = ""
    icon: Path | None = None
    command: str = ""

    @property
    def exec_name(self) -> str:
        if self.exec:
            return Path(self.exec).name
        if self.binary:
            return self.binary.name
        raise ConfigError("'exec' is required when 'dir' is used")

    @property
    def main_executable(self) -> Path:
        if self.binary:
            return self.binary
        assert self.dir is not None
        return self.dir / self.exec

    def validate(self, section: str, check_files: bool = True) -> list[str]:
        problems = []
        if bool(self.binary) == bool(self.dir):
            problems.append(f"[{section}] set exactly one of 'binary' or 'dir'")
        if self.dir and not self.exec:
            problems.append(f"[{section}] 'exec' (path of the executable inside 'dir') is required with 'dir'")
        if check_files:
            if self.binary and not self.binary.is_file():
                problems.append(f"binary not found: {self.binary}")
            if self.dir and not self.dir.is_dir():
                problems.append(f"directory not found: {self.dir}")
            elif self.dir and self.exec and not (self.dir / self.exec).is_file():
                problems.append(f"executable not found: {self.dir / self.exec}")
            if self.icon and not self.icon.is_file():
                problems.append(f"icon not found: {self.icon}")
        return problems


@dataclass
class AppSpec:
    id: str
    name: str
    version: str
    summary: str
    linux: Target | None = None
    windows: Target | None = None
    description: str = ""
    license: str = "LicenseRef-proprietary"
    maintainer: str = ""
    homepage: str = ""
    categories: list[str] = field(default_factory=lambda: ["Utility"])
    deps_auto: bool = True
    deps_deb: list[str] = field(default_factory=list)
    deps_rpm: list[str] = field(default_factory=list)
    formats: list[str] = field(default_factory=lambda: ["deb", "rpm"])
    output_dir: Path = Path("builds")
    base_dir: Path = Path(".")

    # ---- derived values -------------------------------------------------
    @property
    def package_name(self) -> str:
        """Lowercase package name valid for deb/rpm/snap (e.g. "MyGesClient" -> "mygesclient")."""
        name = re.sub(r"[^a-z0-9+.-]+", "-", self.name.lower()).strip("-.+")
        if len(name) < 2:
            raise ConfigError(f"cannot derive a package name from {self.name!r}")
        return name

    def target(self, platform: str) -> Target | None:
        if platform not in PLATFORMS:
            raise ValueError(f"unknown platform {platform!r}")
        return getattr(self, platform)

    @property
    def linux_arch(self) -> tuple[str, str]:
        """(deb_arch, rpm_arch) detected from the Linux executable."""
        if self.linux is None:
            raise ConfigError("no [linux] section in the config")
        return elf.detect_arch(self.linux.main_executable)

    @property
    def windows_arch(self) -> str:
        """"x86", "x64" or "arm64", detected from the Windows executable."""
        if self.windows is None:
            raise ConfigError("no [windows] section in the config")
        return pe.detect_arch(self.windows.main_executable)

    @property
    def file_stem(self) -> str:
        """The app name, safe for file names, keeping its case (e.g. for Windows files)."""
        return re.sub(r"[^\w.+-]+", "-", self.name).strip("-.") or self.package_name

    @property
    def description_text(self) -> str:
        return self.description.strip() or self.summary

    def validate(self, check_files: bool = True, platforms: list[str] | tuple[str, ...] | None = None) -> list[str]:
        """Return a list of human-readable problems (empty if valid).

        `platforms` selects which targets are checked: None means every target the config
        defines (at least one is required), an empty list means the metadata only.
        """
        problems = []
        for attr in ("id", "name", "version", "summary"):
            if not getattr(self, attr).strip():
                problems.append(f"[app] {attr} is required")
        if self.id and not re.fullmatch(r"[A-Za-z_][\w-]*(\.[A-Za-z_][\w-]*){2,}", self.id):
            problems.append(f"[app] id {self.id!r} must be reverse-DNS, e.g. org.example.MyApp")
        if self.version and not re.fullmatch(r"[0-9][A-Za-z0-9.+~]*", self.version):
            problems.append(f"[app] version {self.version!r} must start with a digit and contain no '-' or spaces")
        if not self.formats:
            problems.append("[output] formats must list at least one format")
        if platforms is None:
            platforms = [p for p in PLATFORMS if self.target(p) is not None]
            if not platforms:
                problems.append("describe the app to package in a [linux] or [windows] section")
        for platform in platforms:
            problems += self.target_problems(platform, check_files)
        return problems

    def target_problems(self, platform: str, check_files: bool = True) -> list[str]:
        target = self.target(platform)
        if target is None:
            return [f"no [{platform}] section in the config: it is needed to build {platform} formats"]
        return target.validate(platform, check_files)


def suggest_id(name: str, maintainer: str = "") -> str:
    """Build a plausible reverse-DNS id from the app and maintainer names."""
    owner = re.sub(r"<.*?>", "", maintainer).strip().split(" ")[0].lower() or "example"
    owner = re.sub(r"[^a-z0-9]", "", owner) or "example"
    app = re.sub(r"[^A-Za-z0-9]", "", name) or "App"
    return f"io.github.{owner}.{app}"


# ---- loading ----------------------------------------------------------------

def _path(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value).expanduser()
    return (p if p.is_absolute() else base / p).resolve()


def _str_list(table: dict, key: str, where: str) -> list[str]:
    value = table.get(key, [])
    if isinstance(value, str):
        value = [v.strip() for v in value.split(",") if v.strip()]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"[{where}] {key} must be a list of strings")
    return value


def _target(base_dir: Path, table: dict, where: str) -> Target:
    if not isinstance(table, dict):
        raise ConfigError(f"[{where}] must be a table")
    return Target(
        binary=_path(base_dir, table.get("binary")),
        dir=_path(base_dir, table.get("dir")),
        exec=str(table.get("exec", "")),
        icon=_path(base_dir, table.get("icon")),
        command=str(table.get("command", "")),
    )


def from_dict(data: dict, base_dir: Path) -> AppSpec:
    app = data.get("app", {})
    deps = data.get("deps", {})
    output = data.get("output", {})
    known = {"app", "linux", "windows", "files", "build", "deps", "output"}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")

    linux_table = data.get("linux")
    legacy = {k for k in ("files", "build") if k in data}
    if linux_table is not None and legacy:
        raise ConfigError(f"[{'] and ['.join(sorted(legacy))}] are the old name of [linux]: keep only [linux]")
    if linux_table is None and legacy:
        # Old layout: [files] binary/dir/exec/icon + [build] command.
        linux_table = {**data.get("files", {}), "command": data.get("build", {}).get("command", "")}
    windows_table = data.get("windows")

    spec = AppSpec(
        id=str(app.get("id", "")),
        name=str(app.get("name", "")),
        version=str(app.get("version", "")),
        summary=str(app.get("summary", "")),
        description=str(app.get("description", "")),
        license=str(app.get("license", "LicenseRef-proprietary")),
        maintainer=str(app.get("maintainer", "")),
        homepage=str(app.get("homepage", "")),
        categories=_str_list(app, "categories", "app") or ["Utility"],
        linux=_target(base_dir, linux_table, "linux") if linux_table is not None else None,
        windows=_target(base_dir, windows_table, "windows") if windows_table is not None else None,
        deps_auto=bool(deps.get("auto", True)),
        deps_deb=_str_list(deps, "deb", "deps"),
        deps_rpm=_str_list(deps, "rpm", "deps"),
        formats=_str_list(output, "formats", "output") or ["deb", "rpm"],
        output_dir=_path(base_dir, output.get("dir") or "builds"),
        base_dir=base_dir,
    )
    return spec


def load(path: Path) -> AppSpec:
    path = Path(path)
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"{path}: not found (create one with `packagingonlinux init`)") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    return from_dict(data, path.resolve().parent)


# ---- saving -----------------------------------------------------------------

def _toml_str(value: str) -> str:
    if "\n" in value:
        return '"""\n' + value.replace("\\", "\\\\").replace('"""', '\\"""') + '"""'
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    return f'"{escaped}"'


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return _toml_str(str(value))


def _rel(path: Path | None, base: Path) -> str:
    if path is None:
        return ""
    try:
        return Path(path).resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        import os
        try:
            return Path(os.path.relpath(Path(path).resolve(), base.resolve())).as_posix()
        except ValueError:
            return str(path)


def _target_table(target: Target, base_dir: Path) -> dict:
    return {
        "command": target.command,
        "binary": _rel(target.binary, base_dir), "dir": _rel(target.dir, base_dir),
        "exec": target.exec if target.dir else "", "icon": _rel(target.icon, base_dir),
    }


def to_toml(spec: AppSpec, base_dir: Path) -> str:
    sections: list[tuple[str, dict]] = [
        ("app", {
            "id": spec.id, "name": spec.name, "version": spec.version, "summary": spec.summary,
            "description": spec.description, "license": spec.license,
            "maintainer": spec.maintainer, "homepage": spec.homepage,
            "categories": spec.categories,
        }),
    ]
    for platform in PLATFORMS:
        target = spec.target(platform)
        if target is not None:
            sections.append((platform, _target_table(target, base_dir)))
    sections += [
        ("deps", {"auto": spec.deps_auto, "deb": spec.deps_deb, "rpm": spec.deps_rpm}),
        ("output", {"formats": spec.formats, "dir": _rel(spec.output_dir, base_dir)}),
    ]
    lines = ["# Generated by PackagingOnLinux. Paths are relative to this file."]
    for name, table in sections:
        entries = {k: v for k, v in table.items() if v not in ("", [], None) or isinstance(v, bool)}
        if name == "deps" and entries == {"auto": True}:
            continue
        if not entries and name not in PLATFORMS:  # an empty [windows] still means "build for it"
            continue
        lines.append("")
        lines.append(f"[{name}]")
        lines.extend(f"{k} = {_toml_value(v)}" for k, v in entries.items())
    return "\n".join(lines) + "\n"


def save(spec: AppSpec, path: Path) -> None:
    path = Path(path)
    path.write_text(to_toml(spec, path.resolve().parent), encoding="utf-8")
