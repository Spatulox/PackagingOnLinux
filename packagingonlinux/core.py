"""Shared entry point used by the CLI, the GUI and CI: no packaging logic lives elsewhere."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from packagingonlinux.backend import Backend, BuildContext
from packagingonlinux.config import PLATFORMS, AppSpec, ConfigError
from packagingonlinux.linux import staging as linux_staging
from packagingonlinux.linux.appimage import AppImageBackend
from packagingonlinux.linux.deb import DebBackend
from packagingonlinux.linux.flatpak import FlatpakBackend
from packagingonlinux.linux.rpm import RpmBackend
from packagingonlinux.linux.snap import SnapBackend
from packagingonlinux.linux.tarball import TarballBackend
from packagingonlinux.runner import CommandError, Log, run, temp_dir
from packagingonlinux.windows import staging as windows_staging
from packagingonlinux.windows.nsis import NsisBackend
from packagingonlinux.windows.zip import ZipBackend


# Every packaging backend, by format name. Order = display order in the CLI and the GUI.
# To add a format, write its Backend subclass in linux/ or windows/ and list it here.
BACKENDS: dict[str, Backend] = {b.name: b for b in (
    DebBackend(), RpmBackend(), TarballBackend(), AppImageBackend(), FlatpakBackend(), SnapBackend(),
    ZipBackend(), NsisBackend())}


@dataclass
class ToolStatus:
    name: str
    label: str
    platform: str
    missing: list[str]
    install_hint: str

    @property
    def ok(self) -> bool:
        return not self.missing


@dataclass
class BuildResult:
    packages: dict[str, list[Path]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def doctor() -> list[ToolStatus]:
    return [ToolStatus(b.name, b.label, b.platform, b.missing_tools(), b.install_hint) for b in BACKENDS.values()]


def build_env(spec: AppSpec, platform: str) -> dict[str, str]:
    """Environment of a platform's build command: the caller's, plus the app metadata (e.g.
    to stamp the version into the binary with "$APP_VERSION")."""
    return {**os.environ, "APP_ID": spec.id, "APP_NAME": spec.name, "APP_VERSION": spec.version,
            "APP_PLATFORM": platform}


# platform -> function(spec, stage_root) -> warnings, building that platform's staging tree
STAGERS: dict[str, Callable[[AppSpec, Path], list[str]]] = {
    "linux": linux_staging.build_stage,
    "windows": windows_staging.build_stage,
}


def _prepare(spec: AppSpec, platform: str, stage: Path, log: Log) -> list[str]:
    """Run the platform's build command, validate its target and stage it. Returns warnings."""
    target = spec.target(platform)
    if target is not None and target.command:
        log(f"== {platform} build command")
        run(target.command, log, cwd=spec.base_dir, shell=True, env=build_env(spec, platform))
    problems = spec.target_problems(platform)
    if problems:
        raise ConfigError("\n".join(problems))
    if platform not in STAGERS:
        raise ConfigError(f"{platform} packaging is not supported yet")
    log(f"== {platform} staging")
    return STAGERS[platform](spec, stage)


def build(spec: AppSpec, formats: list[str] | None = None, log: Log = print) -> BuildResult:
    """For each platform with a requested format: run its build command, stage its target
    once, then run each of its backends.

    A failing format (or a failing platform build command) does not stop the others;
    failures are reported in BuildResult.errors.
    """
    formats = formats or spec.formats
    unknown = [f for f in formats if f not in BACKENDS]
    if unknown:
        raise ConfigError(f"unknown format(s): {', '.join(unknown)} (available: {', '.join(BACKENDS)})")
    problems = spec.validate(platforms=())
    if problems:
        raise ConfigError("\n".join(problems))
    result = BuildResult()

    spec.output_dir.mkdir(parents=True, exist_ok=True)
    with temp_dir() as tmp:
        for platform in PLATFORMS:
            names = [f for f in formats if BACKENDS[f].platform == platform]
            if not names:
                continue
            stage = Path(tmp) / platform / "stage"
            try:
                warnings = _prepare(spec, platform, stage, log)
            except (ConfigError, CommandError, OSError, ValueError) as e:
                for name in names:
                    result.errors[name] = str(e)
                    log(f"[{name}] FAILED: {e}")
                continue
            for w in warnings:
                log(f"warning: {w}")
            result.warnings += warnings

            for name in names:
                backend = BACKENDS[name]
                log(f"== {name}")
                missing = backend.missing_tools()
                if missing:
                    msg = f"missing tool(s): {', '.join(missing)}. Install with: {backend.install_hint}"
                    result.errors[name] = msg
                    log(f"[{name}] SKIPPED: {msg}")
                    continue
                workdir = Path(tmp) / platform / name
                workdir.mkdir(parents=True)
                ctx = BuildContext(spec, stage, workdir, spec.output_dir, lambda m, n=name: log(f"[{n}] {m}"))
                try:
                    outputs = backend.build(ctx)
                except (CommandError, OSError, ValueError) as e:
                    result.errors[name] = str(e)
                    log(f"[{name}] FAILED: {e}")
                    continue
                result.packages[name] = outputs
                for p in outputs:
                    log(f"[{name}] OK {p}")
    return result
