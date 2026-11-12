from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("packagingonlinux.gui.qt")
pytest.importorskip("pytestqt")

from packagingonlinux import config  # noqa: E402
from packagingonlinux.gui import app  # noqa: E402
from packagingonlinux.gui.app import MainWindow  # noqa: E402
from packagingonlinux.gui.qt import QMessageBox, QSettings, QToolButton  # noqa: E402
from packagingonlinux.gui.recent import MAX_RECENT, RecentFiles  # noqa: E402
from tests.conftest import make_pe  # noqa: E402


@pytest.fixture(autouse=True)
def settings(monkeypatch, tmp_path):
    """Keep the recent files list in a temporary INI file, never in the user's ~/.config."""
    path = str(tmp_path / "settings.ini")
    monkeypatch.setattr(app, "default_settings", lambda: QSettings(path, QSettings.Format.IniFormat))
    return path


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    """Record message boxes instead of showing them: a modal dialog would block the test forever."""
    shown: list[tuple[str, str]] = []

    def record(parent, title, text, *args, **kwargs):
        shown.append((title, text))
        return QMessageBox.StandardButton.Ok

    for kind in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(QMessageBox, kind, staticmethod(record))
    return shown


@pytest.fixture
def window(qtbot, hello_project):
    w = MainWindow(hello_project)
    qtbot.addWidget(w)
    return w


def test_open_fills_form(window, hello_spec):
    assert window.form.name.text() == "Hello"
    assert window.form.app_id.text() == "org.example.Hello"
    assert window.form.linux.arch.text().startswith("indépendante")
    assert window.form.windows.target() is None
    assert window.formats.formats() == ["deb", "tarball"]


def test_form_save_roundtrip(window, hello_project, hello_spec):
    window.form.summary.setText("Changed summary")
    window.form.deps_deb.setText("libfoo1, libbar2")
    assert window.save()
    again = config.load(hello_project)
    assert again.summary == "Changed summary"
    assert again.deps_deb == ["libfoo1", "libbar2"]
    assert again.linux == hello_spec.linux


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
def test_build_from_gui(window, qtbot, dialogs):
    window.start_build()
    qtbot.waitUntil(lambda: window.worker is None, timeout=30000)
    assert dialogs == []
    log = window.log.toPlainText()
    assert "✔ deb : hello_1.2.3_all.deb" in log
    assert "✔ tarball" in log


def test_license_choice_or_custom(window):
    assert window.form.license.findText("MIT") >= 0
    window.form.license.setCurrentText("MIT")
    assert window.current_spec().license == "MIT"
    window.form.license.setCurrentText("LicenseRef-MyCompany")  # custom value, not in the list
    assert window.current_spec().license == "LicenseRef-MyCompany"


def test_windows_tab_roundtrip(window, hello_project):
    exe = make_pe(hello_project.parent / "hello.exe", 0xAA64)
    window.form.windows.binary.set_path(exe)
    window.form.windows.command.setText("make windows")
    assert window.form.windows.arch.text() == "arm64"
    assert window.save()
    again = config.load(hello_project)
    assert again.windows == config.Target(binary=exe, command="make windows")
    window.form.windows.binary.set_path(None)
    window.form.windows.command.setText("")
    assert window.current_spec().windows is None  # empty tab = no [windows] section


def test_name_suggested_from_windows_exe(qtbot, tmp_path):
    w = MainWindow()
    qtbot.addWidget(w)
    w.form.windows.binary.set_path(make_pe(tmp_path / "Cool.exe"))
    assert w.form.name.text() == "Cool"


def test_formats_grouped_by_platform(window):
    assert set(window.formats.headers) == {"linux", "windows"}
    assert {"zip", "nsis"} <= set(window.formats.checkboxes)


def _recent_entries(window) -> list[str]:
    window._fill_recent_menu()
    return [a.text() for a in window.recent_menu.actions() if not a.isSeparator()]


def test_recent_list_order_dedup_and_limit(tmp_path, settings):
    recent = RecentFiles(QSettings(settings, QSettings.Format.IniFormat))
    a, b = tmp_path / "a.toml", tmp_path / "b.toml"
    recent.add(a)
    # A single entry must survive a reload (INI reads a one-item list back as a string).
    assert RecentFiles(QSettings(settings, QSettings.Format.IniFormat)).paths() == [a]
    recent.add(b)
    recent.add(a)
    assert recent.paths() == [a, b]
    for i in range(MAX_RECENT + 3):
        recent.add(tmp_path / f"{i}.toml")
    assert len(recent.paths()) == MAX_RECENT
    recent.clear()
    assert recent.paths() == []


def test_open_and_save_as_fill_recent_menu(window, hello_project, monkeypatch):
    other = hello_project.with_name("other.toml")
    monkeypatch.setattr(app.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(other), "")))
    assert window.save_as()
    assert window.recent.paths() == [other.resolve(), hello_project.resolve()]
    entries = _recent_entries(window)
    assert entries[0].startswith("&1") and entries[0].endswith("other.toml")
    assert entries[1].startswith("&2") and entries[1].endswith("packaging.toml")
    assert entries[-1] == "Effacer la liste"

    # Picking an entry opens it and moves it to the top.
    window.recent_menu.actions()[1].trigger()
    assert window.config_path == hello_project.resolve()
    assert window.recent.paths()[0] == hello_project.resolve()


def test_recent_menu_hides_missing_files_and_clears(window, hello_project):
    gone = hello_project.with_name("gone.toml")
    window.recent.add(gone)
    assert not any(e.endswith("gone.toml") for e in _recent_entries(window))
    clear = window.recent_menu.actions()[-1]
    clear.trigger()
    assert _recent_entries(window) == ["Aucun fichier récent", "Effacer la liste"]
    assert not window.recent_menu.actions()[-1].isEnabled()


def test_open_toolbar_button_has_recent_dropdown(window):
    buttons = [b for b in window.findChildren(QToolButton) if b.menu() is window.recent_menu]
    assert len(buttons) == 1
    assert buttons[0].popupMode() == QToolButton.ToolButtonPopupMode.MenuButtonPopup


def test_app_id_matches_desktop_file(qapp):
    """The dock icon needs WM_CLASS (X11) and app_id (Wayland) to equal the .desktop file id."""
    root = config.load(Path(__file__).resolve().parent.parent / "packaging.toml")
    assert app.APP_ID == root.id
    name, desktop = qapp.applicationName(), qapp.desktopFileName()
    try:
        app.identify_app(qapp)
        assert qapp.applicationName() == root.id
        assert qapp.desktopFileName() == root.id
    finally:
        qapp.setApplicationName(name)
        qapp.setDesktopFileName(desktop)
