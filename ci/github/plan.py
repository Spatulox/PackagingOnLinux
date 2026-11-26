"""Plan the jobs of the reusable workflow .github/workflows/package.yml.

Reads the caller's packaging.toml and the requested formats, and prints key=value lines
for $GITHUB_OUTPUT:

    formats=deb,rpm,tarball     formats built by the "packages" job (all but snap)
    apt=dpkg-dev rpm            Ubuntu packages that job installs for them
    snap=true                   whether the "snap" job runs
    snap-runner=ubuntu-24.04    the runner of that job: the Ubuntu release of [snap] base
    version=1.2.0~beta          the version the packages get

Usage (PYTHONPATH = a PackagingOnLinux checkout):
    python3 ci/github/plan.py CONFIG [FORMATS] [VERSION]
FORMATS is comma-separated (empty: [output] formats of the config), VERSION replaces
[app] version (empty: keep it). Exits 2 with a message on an unknown format or a bad config.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from packagingonlinux import config
from packagingonlinux.config import ConfigError
from packagingonlinux.core import BACKENDS

# Formats built on their own runner, as root (snapcraft with SNAPCRAFT_BUILD_ENVIRONMENT=host).
SEPARATE = ("snap",)


def snap_runner(base: str) -> str:
    """The GitHub runner of a snap base: core24 -> ubuntu-24.04."""
    m = re.fullmatch(r"core(\d\d)", base)
    if not m:
        raise ConfigError(f"[snap] base {base!r}: no matching GitHub runner (expected coreNN)")
    return f"ubuntu-{m.group(1)}.04"


def plan(config_path: Path, formats: str = "", version: str = "") -> dict[str, str]:
    spec = config.load(config_path)
    wanted = [f.strip() for f in formats.split(",") if f.strip()] or spec.formats
    if not wanted:
        raise ConfigError(f"{config_path}: no format to build (set [output] formats or the formats input)")
    unknown = [f for f in wanted if f not in BACKENDS]
    if unknown:
        raise ConfigError(f"unknown format(s): {', '.join(unknown)} (available: {', '.join(BACKENDS)})")
    if version:
        spec.version = version
    problems = spec.validate(platforms=())
    if problems:
        raise ConfigError("\n".join(problems))
    main = [f for f in wanted if f not in SEPARATE]
    apt = dict.fromkeys(p for f in main for p in BACKENDS[f].apt_packages)
    return {
        "formats": ",".join(main),
        "apt": " ".join(apt),
        "snap": "true" if "snap" in wanted else "false",
        "snap-runner": snap_runner(spec.snap.base) if "snap" in wanted else "",
        "version": spec.version,
    }


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        result = plan(Path(argv[0]), *argv[1:])
    except (ConfigError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
