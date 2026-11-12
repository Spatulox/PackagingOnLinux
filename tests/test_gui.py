from __future__ import annotations

import shutil

import pytest

pytest.importorskip("packagingonlinux.gui.qt")
pytest.importorskip("pytestqt")

from packagingonlinux import config  # noqa: E402
from packagingonlinux.gui.app import MainWindow  # noqa: E402


@pytest.fixture
def window(qtbot, hello_project):
    w = MainWindow(hello_project)
    qtbot.addWidget(w)
    return w


def test_open_fills_form(window, hello_spec):
    assert window.form.name.text() == "Hello"
    assert window.form.app_id.text() == "org.example.Hello"
    assert window.form.arch.text().startswith("indépendante")
    assert window.formats.formats() == ["deb", "tarball"]


def test_form_save_roundtrip(window, hello_project, hello_spec):
    window.form.summary.setText("Changed summary")
    window.form.deps_deb.setText("libfoo1, libbar2")
    assert window.save()
    again = config.load(hello_project)
    assert again.summary == "Changed summary"
    assert again.deps_deb == ["libfoo1", "libbar2"]
    assert again.binary == hello_spec.binary and again.icon == hello_spec.icon


def test_id_is_suggested_from_name(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    w.form.maintainer.setText("Jane Doe")
    w.form.name.setText("Cool App")
    assert w.form.app_id.text() == "io.github.jane.CoolApp"


def test_missing_tool_disables_checkbox(window):
    for name, status in window.formats.status.items():
        assert window.formats.checkboxes[name].isEnabled() == status.ok


@pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="dpkg-deb missing")
def test_build_from_gui(window, qtbot):
    window.start_build()
    qtbot.waitUntil(lambda: window.worker is None, timeout=30000)
    log = window.log.toPlainText()
    assert "✔ deb : hello_1.2.3_all.deb" in log
    assert "✔ tarball" in log


def test_license_choice_or_custom(window):
    assert window.form.license.findText("MIT") >= 0
    window.form.license.setCurrentText("MIT")
    assert window.current_spec().license == "MIT"
    window.form.license.setCurrentText("LicenseRef-MyCompany")  # custom value, not in the list
    assert window.current_spec().license == "LicenseRef-MyCompany"
