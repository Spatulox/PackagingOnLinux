from __future__ import annotations

import pytest

from packagingonlinux.version import bump


@pytest.mark.parametrize("version,release,expected", [
    ("1.2.3", "fix", "1.2.4"),
    ("1.2.3", "minor", "1.3.0"),
    ("1.2.3", "major", "2.0.0"),
    ("0.1.9", "fix", "0.1.10"),
    ("1.4", "fix", "1.4.1"),
    ("2", "minor", "2.1.0"),
    ("1.2.3~rc1", "fix", "1.2.4"),
    ("1.2.3+git20260101", "minor", "1.3.0"),
])
def test_bump(version, release, expected):
    assert bump(version, release) == expected


def test_bump_rejects_bad_input():
    with pytest.raises(ValueError):
        bump("v1.2.3", "fix")
    with pytest.raises(ValueError):
        bump("1.2.3", "patch")
