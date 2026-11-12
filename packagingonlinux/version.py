"""Release versions: bump fix (x.y.Z), minor (x.Y.0) or major (X.0.0), and mark a
pre-release (alpha, beta, rc).

Only the leading numbers count when bumping: anything after them (~rc1, +git...) is
dropped, and a missing minor or fix number counts as 0 (1.4 -> fix -> 1.4.1).

A pre-release is written x.y.z~rcN: deb and rpm sort "~" before everything, even the end
of the string, so 1.3.0~beta2 < 1.3.0~rc1 < 1.3.0.
"""

from __future__ import annotations

import re

RELEASE_TYPES = ("fix", "minor", "major")
KEEP = "keep"  # keep the numbers, only the pre-release stage may change

FINAL = "release"
STAGES = (FINAL, "rc", "beta", "alpha")

_NUMBERS = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_VERSION = re.compile(r"(\d+(?:\.\d+)*)(?:[~.-]?(alpha|beta|rc)(\d*))?(.*)", re.IGNORECASE)


def bump(version: str, release: str) -> str:
    m = _NUMBERS.match(version.strip())
    if not m:
        raise ValueError(f"version {version!r} does not start with a number")
    major, minor, fix = (int(n or 0) for n in m.groups())
    if release == "major":
        return f"{major + 1}.0.0"
    if release == "minor":
        return f"{major}.{minor + 1}.0"
    if release == "fix":
        return f"{major}.{minor}.{fix + 1}"
    raise ValueError(f"unknown release type {release!r} (expected {', '.join(RELEASE_TYPES)})")


def split(version: str) -> tuple[str, str, int]:
    """(numbers, stage, stage number): "1.3.0~rc2" -> ("1.3.0", "rc", 2), "1.3.0" ->
    ("1.3.0", "release", 0). A stage without a number counts as 1."""
    m = _VERSION.match(version.strip())
    if not m:
        raise ValueError(f"version {version!r} does not start with a number")
    base, stage, number, _rest = m.groups()
    if not stage:
        return base, FINAL, 0
    return base, stage.lower(), int(number or 1)


def next_version(version: str, release: str, stage: str = FINAL, number: int = 1) -> str:
    """The version after a release of type `release` (fix, minor, major or KEEP), as a final
    release or as pre-release `stage` number `number`. Keeping the version's own numbers,
    stage and number returns it unchanged (a rebuild)."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r} (expected {', '.join(STAGES)})")
    if number < 1:
        raise ValueError(f"pre-release number must be at least 1, not {number}")
    base, current_stage, current_number = split(version)
    if release == KEEP:
        if stage == current_stage and (stage == FINAL or number == current_number):
            return version
    else:
        base = bump(version, release)
    return base if stage == FINAL else f"{base}~{stage}{number}"
