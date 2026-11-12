"""Command line interface: init, doctor, check, build, gui."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from packagingonlinux import __version__, config, core, staging, winstage
from packagingonlinux.backends import BACKENDS
from packagingonlinux.config import ConfigError
from packagingonlinux.runner import CommandError


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.config)
    if path.exists() and not args.force:
        print(f"{path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    base = path.resolve().parent
    print("Describe the application to package (Enter keeps the default).")
    binary = _ask("Executable file (relative to this folder)")
    name = _ask("Application name", Path(binary).name if binary else "")
    maintainer = _ask("Maintainer (Name <email>)")
    spec = config.AppSpec(
        id=_ask("Application id (reverse-DNS)", config.suggest_id(name, maintainer)),
        name=name,
        version=_ask("Version", "1.0.0"),
        summary=_ask("One-line summary"),
        maintainer=maintainer,
        license=_ask("License (SPDX)", "LicenseRef-proprietary"),
        homepage=_ask("Homepage URL"),
        linux=config.Target(
            binary=base / binary if binary else None,
            icon=(base / icon) if (icon := _ask("Icon file (PNG or SVG, optional)")) else None,
        ),
        categories=[_ask(f"Category ({', '.join(config.MAIN_CATEGORIES)})", "Utility")],
        formats=[f.strip() for f in _ask("Formats", "deb,rpm").split(",") if f.strip()],
    )
    config.save(spec, path)
    print(f"Wrote {path}. Build with: packagingonlinux build -c {path}")
    for p in spec.validate():
        print(f"warning: {p}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    for status in core.doctor():
        if status.ok:
            print(f"  ok       {status.platform:8} {status.name:9} {status.label}")
        else:
            print(f"  missing  {status.platform:8} {status.name:9} {status.label}: needs {', '.join(status.missing)}")
            print(f"           {'':8} {'':9} install: {status.install_hint}")
    return 0


def _check_linux(spec: config.AppSpec) -> bool:
    """Stage the Linux target and run the freedesktop validators. Returns True on failure."""
    import shutil
    import subprocess
    failed = False
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for w in staging.build_stage(spec, stage):
            print(f"warning: {w}")
        validators = [
            ("desktop-file-validate", [str(stage / f"usr/share/applications/{spec.id}.desktop")]),
            ("appstreamcli", ["validate", "--no-net", "--explain",
                              str(stage / f"usr/share/metainfo/{spec.id}.metainfo.xml")]),
        ]
        for tool, tool_args in validators:
            if not shutil.which(tool):
                print(f"skip: {tool} not installed")
                continue
            proc = subprocess.run([tool, *tool_args], capture_output=True, text=True)
            output = (proc.stdout + proc.stderr).strip()
            # appstreamcli also exits non-zero on mere warnings: only "E:" lines are errors.
            bad = proc.returncode != 0 and (tool != "appstreamcli" or "\nE: " in "\n" + output)
            print(f"{tool}: {'FAILED' if bad else 'ok'}")
            if output:
                print("  " + output.replace("\n", "\n  "))
            failed |= bad
    return failed


def cmd_check(args: argparse.Namespace) -> int:
    spec = config.load(Path(args.config))
    problems = spec.validate()
    for p in problems:
        print(f"error: {p}")
    if problems:
        return 1
    failed = False
    targets = []
    if spec.linux is not None:
        failed |= _check_linux(spec)
        arch = spec.linux_arch
        targets.append(f"linux {arch[0]}/{arch[1]}")
    if spec.windows is not None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                for w in winstage.build_stage(spec, Path(tmp)):
                    print(f"warning: {w}")
                targets.append(f"windows {spec.windows_arch}")
            except ValueError as e:
                print(f"error: {e}")
                failed = True
    print(f"{spec.name} {spec.version} ({', '.join(targets)}) -> {', '.join(spec.formats)}")
    return 1 if failed else 0


def cmd_build(args: argparse.Namespace) -> int:
    spec = config.load(Path(args.config))
    if args.output:
        spec.output_dir = Path(args.output).resolve()
    formats = [f.strip() for f in args.format.split(",")] if args.format else None
    result = core.build(spec, formats)
    print()
    for name, paths in result.packages.items():
        for p in paths:
            print(f"built   {name:8} {p}")
    for name, err in result.errors.items():
        print(f"failed  {name:8} {err}", file=sys.stderr)
    return 0 if result.ok else 1


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from packagingonlinux.gui.app import main as gui_main
    except ImportError as e:
        print(f"GUI unavailable ({e}). Install it with: pip install 'packagingonlinux[gui]'", file=sys.stderr)
        return 1
    return gui_main([args.config] if args.config else [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="packagingonlinux",
        description="Package a prebuilt Linux or Windows application as " + ", ".join(BACKENDS) + ".",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def with_config(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("-c", "--config", default=config.CONFIG_NAME, help="path to packaging.toml")
        return p

    p = with_config(sub.add_parser("init", help="create a packaging.toml interactively"))
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)
    sub.add_parser("doctor", help="show which formats can be built on this machine").set_defaults(func=cmd_doctor)
    with_config(sub.add_parser("check", help="validate the config and generated metadata")).set_defaults(func=cmd_check)
    p = with_config(sub.add_parser("build", help="build packages"))
    p.add_argument("-f", "--format", help="comma-separated formats (default: [output] formats)")
    p.add_argument("-o", "--output", help="output directory (default: [output] dir)")
    p.set_defaults(func=cmd_build)
    p = sub.add_parser("gui", help="open the graphical interface")
    p.add_argument("config", nargs="?", help="packaging.toml to open")
    p.set_defaults(func=cmd_gui)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ConfigError, CommandError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
