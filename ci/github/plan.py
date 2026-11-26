"""Plan the jobs of the reusable workflow .github/workflows/package.yml.

Reads the caller's packaging.toml and the requested formats, and prints key=value lines
for $GITHUB_OUTPUT:

    formats=deb,rpm,tarball     formats built by the "packages" job (all but snap)
    apt=dpkg-dev rpm            Ubuntu/Debian packages that job installs for them
    dnf=dpkg dpkg-dev rpm-build the same on Fedora (for a build image based on it)
    snap=true                   whether the "snap" job runs
    snap-runner=ubuntu-24.04    the runner of that job: the Ubuntu release of [snap] base
    version=1.2.0~beta          the version the packages get

Usage (PYTHONPATH = a PackagingOnLinux checkout):
    python3 ci/github/plan.py CONFIG [FORMATS] [VERSION] [CONTAINER]
FORMATS is comma-separated (empty: [output] formats of the config), VERSION replaces
[app] version (empty: keep it), CONTAINER is "true" when the build runs in the project's
build image (dockerfile or image input). Exits 2 with a message on an unknown format, a
bad config, or a format that can't be built in a container.
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


def plan(config_path: Path, formats: str = "", version: str = "", container: bool = False) -> dict[str, str]:
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
    if container and "snap" in wanted:
        # snapcraft can't run in Docker, and on the runner the build command would lack the
        # toolchain of the build image.
        raise ConfigError("the snap format can't be built with a build image (dockerfile or image input)")
    main = [f for f in wanted if f not in SEPARATE]
    apt = dict.fromkeys(p for f in main for p in BACKENDS[f].apt_packages)
    dnf = dict.fromkeys(p for f in main for p in BACKENDS[f].dnf_packages)
    return {
        "formats": ",".join(main),
        "apt": " ".join(apt),
        "dnf": " ".join(dnf),
        "snap": "true" if "snap" in wanted else "false",
        "snap-runner": snap_runner(spec.snap.base) if "snap" in wanted else "",
        "version": spec.version,
    }


def main(argv: list[str]) -> int:
    if not 1 <= len(argv) <= 4:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        result = plan(Path(argv[0]), *argv[1:3], *(a == "true" for a in argv[3:]))
    except (ConfigError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
