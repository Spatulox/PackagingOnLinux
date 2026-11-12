from __future__ import annotations

import pytest

from packagingonlinux.version import KEEP, bump, next_version, split


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


@pytest.mark.parametrize("version,expected", [
    ("1.2.3", ("1.2.3", "release", 0)),
    ("1.3.0~rc2", ("1.3.0", "rc", 2)),
    ("1.3.0~beta", ("1.3.0", "beta", 1)),
    ("2.0~alpha10", ("2.0", "alpha", 10)),
    ("1.2.3+git20260101", ("1.2.3", "release", 0)),
])
def test_split(version, expected):
    assert split(version) == expected


@pytest.mark.parametrize("version,release,stage,number,expected", [
    ("1.2.3", "fix", "release", 1, "1.2.4"),
    ("1.2.3", "minor", "rc", 1, "1.3.0~rc1"),
    ("1.2.3", "major", "alpha", 2, "2.0.0~alpha2"),
    ("1.3.0~rc1", KEEP, "rc", 2, "1.3.0~rc2"),
    ("1.3.0~beta2", KEEP, "rc", 1, "1.3.0~rc1"),
    ("1.3.0~rc2", KEEP, "release", 1, "1.3.0"),
    ("1.3.0~rc2", KEEP, "rc", 2, "1.3.0~rc2"),        # same stage and number: rebuild
    ("1.2.3+git20260101", KEEP, "release", 1, "1.2.3+git20260101"),
    ("1.3.0~rc2", "fix", "release", 1, "1.3.1"),
])
def test_next_version(version, release, stage, number, expected):
    assert next_version(version, release, stage, number) == expected


def test_next_version_rejects_bad_input():
    with pytest.raises(ValueError):
        next_version("1.2.3", "fix", "gamma")
    with pytest.raises(ValueError):
        next_version("1.2.3", "fix", "rc", 0)
