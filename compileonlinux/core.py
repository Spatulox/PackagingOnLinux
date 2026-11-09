"""Shared entry point used by the CLI, the GUI and CI: no packaging logic lives elsewhere."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from compileonlinux import staging
from compileonlinux.backends import BACKENDS, BuildContext
from compileonlinux.config import AppSpec, ConfigError
from compileonlinux.runner import CommandError, Log, run


@dataclass
class ToolStatus:
    name: str
    label: str
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
    return [ToolStatus(b.name, b.label, b.missing_tools(), b.install_hint) for b in BACKENDS.values()]


def build(spec: AppSpec, formats: list[str] | None = None, log: Log = print) -> BuildResult:
    """Run the optional build command, stage the app once, then run each requested backend.

    A failing format does not stop the others; failures are reported in BuildResult.errors.
    """
    formats = formats or spec.formats
    unknown = [f for f in formats if f not in BACKENDS]
    if unknown:
        raise ConfigError(f"unknown format(s): {', '.join(unknown)} (available: {', '.join(BACKENDS)})")
    result = BuildResult()

    if spec.build_command:
        log("== build command")
        run(spec.build_command, log, cwd=spec.base_dir, shell=True)

    problems = spec.validate()
    if problems:
        raise ConfigError("\n".join(problems))

    spec.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="compileonlinux-") as tmp:
        stage = Path(tmp) / "stage"
        log("== staging")
        result.warnings += staging.build_stage(spec, stage)
        for w in result.warnings:
            log(f"warning: {w}")

        for name in formats:
            backend = BACKENDS[name]
            log(f"== {name}")
            missing = backend.missing_tools()
            if missing:
                msg = f"missing tool(s): {', '.join(missing)}. Install with: {backend.install_hint}"
                result.errors[name] = msg
                log(f"[{name}] SKIPPED: {msg}")
                continue
            workdir = Path(tmp) / name
            workdir.mkdir()
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

