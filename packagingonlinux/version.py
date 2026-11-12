"""Release version bumping: fix (x.y.Z), minor (x.Y.0) or major (X.0.0).

Only the leading numbers count: anything after them (~rc1, +git...) is dropped, and a
missing minor or fix number counts as 0 (1.4 -> fix -> 1.4.1).
"""

from __future__ import annotations

import re

RELEASE_TYPES = ("fix", "minor", "major")


def bump(version: str, release: str) -> str:
    m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", version.strip())
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
