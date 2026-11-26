"""ci/github/plan.py, which plans the jobs of the reusable workflow package.yml."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from packagingonlinux.config import ConfigError
from packagingonlinux.core import BACKENDS

ROOT = Path(__file__).resolve().parent.parent


def _plan_module():
    spec = importlib.util.spec_from_file_location("ci_plan", ROOT / "ci/github/plan.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plan_module = _plan_module()


def test_formats_from_the_config(hello_project):
    assert plan_module.plan(hello_project) == {
        "formats": "deb,tarball", "apt": "dpkg-dev", "snap": "false", "snap-runner": "", "version": "1.2.3",
    }


def test_snap_gets_its_own_job_on_the_runner_of_its_base(hello_project):
    hello_project.write_text(hello_project.read_text() + '\n[snap]\nbase = "core22"\n')
    result = plan_module.plan(hello_project, "snap,flatpak,deb, rpm", "2.0.0~rc")
    assert result["formats"] == "flatpak,deb,rpm"
    assert result["apt"] == "flatpak flatpak-builder librsvg2-common dpkg-dev rpm"
    assert (result["snap"], result["snap-runner"], result["version"]) == ("true", "ubuntu-22.04", "2.0.0~rc")


def test_only_snap(hello_project):
    result = plan_module.plan(hello_project, "snap")
    assert (result["formats"], result["apt"], result["snap-runner"]) == ("", "", "ubuntu-24.04")


@pytest.mark.parametrize("formats,version,message", [
    ("deb,dmg", "", "unknown format(s): dmg"),
    ("deb", "v1.0-beta", "[app] version"),
])
def test_bad_input(hello_project, formats, version, message):
    with pytest.raises(ConfigError, match=message.replace("[", r"\[").replace("(", r"\(").replace(")", r"\)")):
        plan_module.plan(hello_project, formats, version)


def test_main_prints_github_outputs(hello_project, capsys):
    assert plan_module.main([str(hello_project), "", "3.0.0"]) == 0
    assert "formats=deb,tarball\n" in capsys.readouterr().out
    assert plan_module.main([str(hello_project), "nope"]) == 2


def test_every_backend_with_tools_says_how_ci_installs_them():
    # A new backend must list its Ubuntu packages, or package.yml can't build it.
    for name, backend in BACKENDS.items():
        if backend.required_tools and name not in plan_module.SEPARATE:
            assert backend.apt_packages, name
