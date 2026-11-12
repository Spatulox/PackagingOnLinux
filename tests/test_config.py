from __future__ import annotations

from pathlib import Path

import pytest

from packagingonlinux import config
from packagingonlinux.linux import elf
from packagingonlinux.config import ConfigError


def test_load_resolves_paths_relative_to_config(hello_spec, hello_project):
    base = hello_project.parent
    assert hello_spec.linux.binary == base / "hello"
    assert hello_spec.linux.icon == base / "hello.png"
    assert hello_spec.windows is None
    assert hello_spec.output_dir == base / "out"
    assert hello_spec.package_name == "hello"
    assert hello_spec.validate() == []


def test_roundtrip_keeps_everything(hello_spec, hello_project):
    hello_spec.deps_deb = ["libfoo1"]
    hello_spec.linux.command = "make"
    hello_spec.windows = config.Target(binary=hello_project.parent / "win/hello.exe",
                                       command="make windows")
    config.save(hello_spec, hello_project)
    again = config.load(hello_project)
    for attr in ("id", "name", "version", "summary", "description", "license", "maintainer",
                 "categories", "linux", "windows", "deps_deb", "formats", "output_dir"):
        assert getattr(again, attr) == getattr(hello_spec, attr), attr
    text = hello_project.read_text()
    assert '[linux]\ncommand = "make"\nbinary = "hello"' in text
    assert '[windows]\ncommand = "make windows"\nbinary = "win/hello.exe"' in text
    assert "[files]" not in text and "[build]" not in text


def test_flatpak_options_roundtrip(hello_spec, hello_project):
    config.save(hello_spec, hello_project)
    assert "[flatpak]" not in hello_project.read_text()  # defaults are not written
    hello_spec.flatpak.runtime_version = "25.08"
    hello_spec.flatpak.finish_args = []
    config.save(hello_spec, hello_project)
    assert '[flatpak]\nruntime_version = "25.08"\nfinish_args = []\n' in hello_project.read_text()
    assert config.load(hello_project).flatpak == hello_spec.flatpak


def test_snap_options_roundtrip(hello_spec, hello_project):
    hello_spec.snap.confinement = "classic"
    hello_spec.snap.extensions = ["gnome"]
    config.save(hello_spec, hello_project)
    text = hello_project.read_text()
    assert '[snap]\nconfinement = "classic"\nextensions = ["gnome"]\n' in text
    assert config.load(hello_project).snap == hello_spec.snap


def test_flatpak_unknown_key_rejected(hello_project):
    hello_project.write_text(hello_project.read_text() + '\n[flatpak]\nruntimeversion = "25.08"\n')
    with pytest.raises(config.ConfigError, match="runtimeversion"):
        config.load(hello_project)


def test_old_files_and_build_sections_are_read_as_linux(tmp_path):
    spec = config.from_dict({
        "app": {"id": "org.example.Old", "name": "Old", "version": "1", "summary": "s"},
        "files": {"binary": "old", "icon": "old.png"},
        "build": {"command": "make"},
    }, tmp_path)
    assert spec.linux == config.Target(binary=tmp_path / "old", icon=tmp_path / "old.png", command="make")
    assert spec.windows is None


def test_mixing_old_and_new_sections_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="old name of \\[linux\\]"):
        config.from_dict({"linux": {"binary": "a"}, "files": {"binary": "b"}}, tmp_path)


def test_validate_only_checks_requested_platforms(hello_spec):
    hello_spec.windows = config.Target()  # empty: invalid
    assert hello_spec.validate(platforms=["linux"]) == []
    assert any("[windows] set exactly one" in p for p in hello_spec.validate())
    hello_spec.linux = None
    assert any("no [linux] section" in p for p in hello_spec.validate(platforms=["linux"]))
    assert hello_spec.validate(platforms=[]) == []


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
    assert hello_spec.linux_arch == ("all", "noarch")


def test_set_version_keeps_comments_and_layout(tmp_path):
    path = tmp_path / "packaging.toml"
    original = (
        "# header comment\n"
        "[app]\n"
        "id = \"org.example.Hello\"  # inline\n"
        "version = \"1.2.3\"   # bumped by the GUI\n"
        "description = \"\"\"\nversion = \"9.9.9\" inside a string\n\"\"\"\n"
        "\n[linux]\n# keep me\nversion = \"not the app\"\n"
    )
    path.write_text(original)
    config.set_version(path, "1.2.4")
    assert path.read_text() == original.replace('version = "1.2.3"', 'version = "1.2.4"')


def test_set_version_without_version_line_writes_nothing(tmp_path):
    path = tmp_path / "packaging.toml"
    path.write_text("[app]\nid = \"org.example.Hello\"\n")
    with pytest.raises(ConfigError):
        config.set_version(path, "1.0.1")
    assert path.read_text() == "[app]\nid = \"org.example.Hello\"\n"
