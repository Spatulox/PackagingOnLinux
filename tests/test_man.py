from __future__ import annotations

import dataclasses
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

from packagingonlinux import cli, config
from packagingonlinux.core import BACKENDS

ROOT = Path(__file__).resolve().parent.parent
MAN_DIR = ROOT / "docs/man"


def _gen_man():
    spec = importlib.util.spec_from_file_location("gen_man", ROOT / "tools/gen_man.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_man_page_is_up_to_date():
    page = (MAN_DIR / "packagingonlinux.1").read_text(encoding="utf-8")
    assert page == _gen_man().render(), "docs/man/packagingonlinux.1 is out of date: run python3 tools/gen_man.py"


def test_man_page_documents_every_command_and_format():
    page = _gen_man().render()
    for command in ("init", "doctor", "check", "build", "gui"):
        assert f".SS {command}\n" in page
    for name in BACKENDS:
        assert f"\\fB{name}\\fR" in page
    assert "\\fB\\-f\\fR, \\fB\\-\\-format\\fR \\fIFORMATS\\fR" in page


def test_roff_escaping():
    esc = _gen_man().esc
    assert esc("-f a\\b") == "\\-f a\\eb"
    assert esc(".hidden\n'quote") == "\\&.hidden\n\\&'quote"


@pytest.mark.skipif(not shutil.which("groff"), reason="groff not installed")
@pytest.mark.parametrize("page", sorted(MAN_DIR.glob("*.[1-9]")), ids=lambda p: p.name)
def test_man_pages_render_without_warnings(page):
    proc = subprocess.run(["groff", "-man", "-Tutf8", "-ww", "-z", str(page)], capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stderr == ""


def test_help_lists_formats_examples_and_exit_status(capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--help"])
    assert exit_info.value.code == 0
    out = capsys.readouterr().out
    for name in BACKENDS:
        assert f"\n  {name} " in out
    assert "packagingonlinux build -f deb,rpm -o dist" in out
    assert "exit status:" in out


def _documented_keys(page: str, section: str) -> set[str]:
    """The \\fBkey\\fR entries of a '.SH "[section] SECTION"' of packaging.toml(5)."""
    start = page.index(f'.SH "[{section}] SECTION"\n')
    end = page.find("\n.SH ", start + 1)
    body = page[start:end if end != -1 else None]
    return {line.split("\\fR")[0][3:] for line in body.splitlines() if line.startswith("\\fB")}


def test_config_page_documents_every_section_and_key():
    page = (MAN_DIR / "packaging.toml.5").read_text(encoding="utf-8")
    target_keys = {f.name for f in dataclasses.fields(config.Target)}
    assert target_keys <= _documented_keys(page, "linux")
    for section in ("app", "windows", "deps", "output"):
        assert f'.SH "[{section}] SECTION"' in page
    spec = config.AppSpec(id="org.example.App", name="App", version="1", summary="s")
    for section in config.OPTION_SECTIONS:  # per-format options: [flatpak]...
        keys = set(vars(getattr(spec, section)))
        missing = keys - _documented_keys(page, section)
        assert not missing, f"[{section}] keys missing from docs/man/packaging.toml.5: {missing}"
