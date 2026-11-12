"""Command line interface: init, doctor, check, build, gui."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from packagingonlinux import __version__, config, core
from packagingonlinux.config import ConfigError
from packagingonlinux.core import BACKENDS
from packagingonlinux.linux import staging as linux_staging
from packagingonlinux.runner import CommandError
from packagingonlinux.windows import staging as windows_staging


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
    print(f"PackagingOnLinux {__version__}")
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
        for w in linux_staging.build_stage(spec, stage):
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
                for w in windows_staging.build_stage(spec, Path(tmp)):
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


DESCRIPTION = """\
Package a prebuilt application (a binary or an install folder, one per platform) into
Linux and Windows formats, without root and from any distribution. The app is described
once in a packaging.toml file (see packaging.toml(5)), shared by this command, the
graphical interface and CI."""

# (command line, what it does): shown by --help and in the man page.
EXAMPLES = [
    ("packagingonlinux init", "write a packaging.toml in the current directory, asking questions"),
    ("packagingonlinux doctor", "list the formats this machine can build, and how to get the others"),
    ("packagingonlinux check -c app/packaging.toml", "validate a config without building anything"),
    ("packagingonlinux build", "build the formats listed in [output] formats of ./packaging.toml"),
    ("packagingonlinux build -f deb,rpm -o dist", "build only the deb and rpm packages, into dist/"),
    ("packagingonlinux gui app/packaging.toml", "edit a config in the graphical interface"),
]

EXIT_STATUS = [
    ("0", "success"),
    ("1", "check found a problem, a format failed to build, init refused to overwrite a file, "
          "or the GUI is not available"),
    ("2", "invalid command line or config (unreadable packaging.toml, unknown format...)"),
    ("130", "interrupted (Ctrl+C)"),
]

ENVIRONMENT = [
    ("PACKAGINGONLINUX_APPIMAGE_RUNTIME",
     "path to an AppImage type2 runtime to use instead of downloading the pinned release"),
    ("XDG_CACHE_HOME", "where the downloaded AppImage runtime is cached (default: ~/.cache)"),
]

FILES = [
    ("packaging.toml", "the config read by default, in the current directory"),
    ("$XDG_CACHE_HOME/packagingonlinux/", "cache of the AppImage runtime"),
]


def formats_help() -> list[tuple[str, str, str]]:
    """(format, what it builds and from which section, how to install its tools) per backend."""
    rows = []
    for b in BACKENDS.values():
        text = f"{b.label}, from [{b.platform}]"
        if b.required_tools:
            text += f"; needs {', '.join(b.required_tools)}"
        rows.append((b.name, text, b.install_hint if b.required_tools else ""))
    return rows


def _epilog() -> str:
    def block(title: str, rows: list[tuple[str, str]]) -> str:
        width = max(len(k) for k, _ in rows) + 2
        return title + ":\n" + "\n".join(f"  {k:{width}}{v}" for k, v in rows)
    rows = formats_help()
    indent = " " * (max(len(name) for name, _, _ in rows) + 4)
    formats = [(name, text + (f"\n{indent}install: {hint}" if hint else "")) for name, text, hint in rows]
    return "\n\n".join([
        block("formats", formats),
        "examples:\n" + "\n".join(f"  {cmd}\n      {what}" for cmd, what in EXAMPLES),
        block("exit status", EXIT_STATUS),
        "Run 'packagingonlinux COMMAND --help' for a command's options.\n"
        "Full manual: man packagingonlinux",
    ])


def build_parser() -> argparse.ArgumentParser:
    """The command line parser (also the source of the man page, see tools/gen_man.py)."""
    parser = argparse.ArgumentParser(
        prog="packagingonlinux",
        description=DESCRIPTION,
        epilog=_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def command(name: str, summary: str, description: str) -> argparse.ArgumentParser:
        return sub.add_parser(name, help=summary, description=description)

    def with_config(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
        p.add_argument("-c", "--config", default=config.CONFIG_NAME, metavar="PATH",
                       help="path to the config (default: packaging.toml in the current directory)")
        return p

    p = with_config(command(
        "init", "create a packaging.toml interactively",
        "Ask for the executable, name, id, version, maintainer, license, icon, category and "
        "formats, then write a [linux] config. Refuses to overwrite an existing file."))
    p.add_argument("--force", action="store_true", help="overwrite the config if it exists")
    p.set_defaults(func=cmd_init)

    command(
        "doctor", "show which formats can be built on this machine",
        "Print the version, then one line per format: ok, or the missing tools and the command "
        "that installs them. Always exits 0.").set_defaults(func=cmd_doctor)

    with_config(command(
        "check", "validate the config and generated metadata",
        "Report missing or invalid fields and files, then generate the Linux .desktop and "
        "AppStream metainfo files in a temporary directory and run desktop-file-validate and "
        "appstreamcli on them (skipped when not installed). Builds and writes nothing.",
    )).set_defaults(func=cmd_check)

    p = with_config(command(
        "build", "build packages",
        "For each platform that has a requested format, run its build command, then build "
        "every requested format into the output directory. A format that fails, or whose "
        "tools are missing, does not stop the others: failures are listed at the end and the "
        "exit status is 1."))
    p.add_argument("-f", "--format", metavar="FORMATS",
                   help="comma-separated formats to build (default: [output] formats of the config)")
    p.add_argument("-o", "--output", metavar="DIR",
                   help="output directory (default: [output] dir of the config)")
    p.set_defaults(func=cmd_build)

    p = command(
        "gui", "open the graphical interface",
        "Open the graphical interface (in French), on CONFIG if given. Needs PyQt6 or PySide6.")
    p.add_argument("config", nargs="?", metavar="CONFIG", help="packaging.toml to open")
    p.set_defaults(func=cmd_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
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
