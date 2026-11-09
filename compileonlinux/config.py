"""packaging.toml <-> AppSpec.

The TOML file is the exchange format between the GUI, the CLI and CI. Relative paths in
it are resolved against the directory that contains the file.

Schema:
    [app]     id, name, version, summary, description, license, maintainer, homepage, categories
    [files]   binary | dir (+ exec), icon
    [build]   command               (optional, run before packaging, with $APP_ID,
                                     $APP_NAME and $APP_VERSION set)
    [deps]    auto, deb, rpm        (optional)
    [output]  formats, dir
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from compileonlinux import elf

CONFIG_NAME = "packaging.toml"

# Main categories from the freedesktop menu spec.
MAIN_CATEGORIES = [
    "AudioVideo", "Audio", "Video", "Development", "Education", "Game", "Graphics",
    "Network", "Office", "Science", "Settings", "System", "Utility",
]


class ConfigError(ValueError):
    pass


@dataclass
class AppSpec:
    id: str
    name: str
    version: str
    summary: str
    binary: Path | None = None
    dir: Path | None = None
    exec: str = ""
    icon: Path | None = None
    description: str = ""
    license: str = "LicenseRef-proprietary"
    maintainer: str = ""
    homepage: str = ""
    categories: list[str] = field(default_factory=lambda: ["Utility"])
    build_command: str = ""
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

    @property
    def exec_name(self) -> str:
        if self.exec:
            return Path(self.exec).name
        if self.binary:
            return self.binary.name
        raise ConfigError("[files] needs 'exec' when 'dir' is used")

    @property
    def main_executable(self) -> Path:
        if self.binary:
            return self.binary
        assert self.dir is not None
        return self.dir / self.exec

    @property
    def arch(self) -> tuple[str, str]:
        """(deb_arch, rpm_arch) detected from the main executable."""
        return elf.detect_arch(self.main_executable)

    @property
    def description_text(self) -> str:
        return self.description.strip() or self.summary

    def validate(self, check_files: bool = True) -> list[str]:
        """Return a list of human-readable problems (empty if valid)."""
        problems = []
        for attr in ("id", "name", "version", "summary"):
            if not getattr(self, attr).strip():
                problems.append(f"[app] {attr} is required")
        if self.id and not re.fullmatch(r"[A-Za-z_][\w-]*(\.[A-Za-z_][\w-]*){2,}", self.id):
            problems.append(f"[app] id {self.id!r} must be reverse-DNS, e.g. org.example.MyApp")
        if self.version and not re.fullmatch(r"[0-9][A-Za-z0-9.+~]*", self.version):
            problems.append(f"[app] version {self.version!r} must start with a digit and contain no '-' or spaces")
        if bool(self.binary) == bool(self.dir):
            problems.append("[files] set exactly one of 'binary' or 'dir'")
        if self.dir and not self.exec:
            problems.append("[files] 'exec' (path of the executable inside 'dir') is required with 'dir'")
        if not self.formats:
            problems.append("[output] formats must list at least one format")
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


def from_dict(data: dict, base_dir: Path) -> AppSpec:
    app = data.get("app", {})
    files = data.get("files", {})
    build = data.get("build", {})
    deps = data.get("deps", {})
    output = data.get("output", {})
    known = {"app", "files", "build", "deps", "output"}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"unknown section(s): {', '.join(sorted(unknown))}")
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
        binary=_path(base_dir, files.get("binary")),
        dir=_path(base_dir, files.get("dir")),
        exec=str(files.get("exec", "")),
        icon=_path(base_dir, files.get("icon")),
        build_command=str(build.get("command", "")),
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
        raise ConfigError(f"{path}: not found (create one with `compileonlinux init`)") from None
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


def to_toml(spec: AppSpec, base_dir: Path) -> str:
    sections: list[tuple[str, dict]] = [
        ("app", {
            "id": spec.id, "name": spec.name, "version": spec.version, "summary": spec.summary,
            "description": spec.description, "license": spec.license,
            "maintainer": spec.maintainer, "homepage": spec.homepage,
            "categories": spec.categories,
        }),
        ("files", {
            "binary": _rel(spec.binary, base_dir), "dir": _rel(spec.dir, base_dir),
            "exec": spec.exec if spec.dir else "", "icon": _rel(spec.icon, base_dir),
        }),
        ("build", {"command": spec.build_command}),
        ("deps", {"auto": spec.deps_auto, "deb": spec.deps_deb, "rpm": spec.deps_rpm}),
        ("output", {"formats": spec.formats, "dir": _rel(spec.output_dir, base_dir)}),
    ]
    lines = ["# Generated by CompileOnLinux. Paths are relative to this file."]
    for name, table in sections:
        entries = {k: v for k, v in table.items() if v not in ("", [], None) or isinstance(v, bool)}
        if name == "deps" and entries == {"auto": True}:
            continue
        if not entries:
            continue
        lines.append("")
        lines.append(f"[{name}]")
        lines.extend(f"{k} = {_toml_value(v)}" for k, v in entries.items())
    return "\n".join(lines) + "\n"


def save(spec: AppSpec, path: Path) -> None:
    path = Path(path)
    path.write_text(to_toml(spec, path.resolve().parent), encoding="utf-8")
