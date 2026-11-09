from __future__ import annotations

from pathlib import Path

import pytest

from compileonlinux import config, elf
from compileonlinux.config import ConfigError


def test_load_resolves_paths_relative_to_config(hello_spec, hello_project):
    base = hello_project.parent
    assert hello_spec.binary == base / "hello"
    assert hello_spec.icon == base / "hello.png"
    assert hello_spec.output_dir == base / "out"
    assert hello_spec.package_name == "hello"
    assert hello_spec.validate() == []


def test_roundtrip_keeps_everything(hello_spec, hello_project):
    hello_spec.deps_deb = ["libfoo1"]
    hello_spec.build_command = "make"
    config.save(hello_spec, hello_project)
    again = config.load(hello_project)
    for attr in ("id", "name", "version", "summary", "description", "license", "maintainer",
                 "categories", "binary", "icon", "deps_deb", "build_command", "formats", "output_dir"):
        assert getattr(again, attr) == getattr(hello_spec, attr), attr
    assert 'binary = "hello"' in hello_project.read_text()


@pytest.mark.parametrize("field,value,message", [
    ("id", "hello", "reverse-DNS"),
    ("version", "1.0-beta", "version"),
    ("summary", "", "summary is required"),
])
def test_validate_reports_problems(hello_spec, field, value, message):
    setattr(hello_spec, field, value)
    assert any(message in p for p in hello_spec.validate())


def test_unknown_section_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown section"):
        config.from_dict({"app": {}, "typo": {}}, tmp_path)


def test_package_name_is_distro_safe(hello_spec):
    hello_spec.name = "My Ges_Client!"
    assert hello_spec.package_name == "my-ges-client"


def test_suggest_id():
    assert config.suggest_id("My App", "Jane Doe <j@d.org>") == "io.github.jane.MyApp"


def _elf_header(machine: int) -> bytes:
    return b"\x7fELF\x02\x01\x01" + b"\x00" * 11 + machine.to_bytes(2, "little")


@pytest.mark.parametrize("machine,expected", [(0x3E, ("amd64", "x86_64")), (0xB7, ("arm64", "aarch64"))])
def test_detect_arch(tmp_path: Path, machine, expected):
    f = tmp_path / "bin"
    f.write_bytes(_elf_header(machine) + b"\x00" * 64)
    assert elf.detect_arch(f) == expected


def test_detect_arch_script_is_independent(hello_spec):
    assert hello_spec.arch == ("all", "noarch")
