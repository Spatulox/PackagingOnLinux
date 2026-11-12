from __future__ import annotations

import sys
from pathlib import Path


from packagingonlinux import __version__, config
from packagingonlinux.backends import BACKENDS
from packagingonlinux.config import ConfigError
from packagingonlinux.gui.form import AppForm, PathField
from packagingonlinux.gui.formats import FormatsPanel
from packagingonlinux.gui.qt import (
    QAction, QApplication, QDesktopServices, QFileDialog, QFontDatabase, QFormLayout, QHBoxLayout,
    QKeySequence, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSplitter, Qt,
    QUrl, QVBoxLayout, QWidget,
)
from packagingonlinux.gui.worker import BuildWorker

TOML_FILTER = "Configuration PackagingOnLinux (packaging.toml *.toml)"


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path | None = None):
        super().__init__()
        self.config_path: Path | None = None
        self.worker: BuildWorker | None = None
        self.resize(820, 900)

        self.form = AppForm()
        self.formats = FormatsPanel()
        self.output = PathField("Dossier de sortie", directory=True)
        self.output.set_path(Path.cwd() / "dist")
        out_form = QFormLayout()
        out_form.addRow("Dossier de sortie", self.output)

        self.build_button = QPushButton("Construire les paquets")
        self.build_button.setDefault(True)
        self.build_button.setMinimumHeight(36)
        self.build_button.clicked.connect(self.start_build)
        self.open_output_button = QPushButton("Ouvrir le dossier de sortie")
        self.open_output_button.clicked.connect(self.open_output)
        buttons = QHBoxLayout()
        buttons.addWidget(self.build_button, 1)
        buttons.addWidget(self.open_output_button)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.addWidget(self.form)
        top_layout.addWidget(self.formats)
        top_layout.addLayout(out_form)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(top)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log.setPlaceholderText("Le journal de construction s'affichera ici.")

        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addLayout(buttons)
        bottom_layout.addWidget(self.log)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(scroll)
        splitter.addWidget(bottom)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._make_actions()
        self.formats.set_formats(["deb", "rpm"])
        if config_path:
            self.open_config(Path(config_path))
        self._update_title()

    # ---- menus ----------------------------------------------------------------
    def _make_actions(self) -> None:
        toolbar = self.addToolBar("Fichier")
        toolbar.setMovable(False)
        menu = self.menuBar().addMenu("&Fichier")
        for text, shortcut, slot in [
            ("Nouveau", QKeySequence.StandardKey.New, self.new_config),
            ("Ouvrir…", QKeySequence.StandardKey.Open, self.ask_open),
            ("Enregistrer", QKeySequence.StandardKey.Save, self.save),
            ("Enregistrer sous…", QKeySequence.StandardKey.SaveAs, self.save_as),
        ]:
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)
            toolbar.addAction(action)
        menu.addSeparator()
        quit_action = QAction("Quitter", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _update_title(self) -> None:
        name = str(self.config_path) if self.config_path else "nouvelle configuration"
        self.setWindowTitle(f"PackagingOnLinux {__version__} — {name}")

    def _base_dir(self) -> Path:
        return self.config_path.parent if self.config_path else Path.cwd()

    def current_spec(self) -> config.AppSpec:
        output = self.output.path() or self._base_dir() / "dist"
        return self.form.to_spec(self._base_dir(), self.formats.formats(), output)

    # ---- file actions ----------------------------------------------------------
    def new_config(self) -> None:
        self.config_path = None
        self.form.set_spec(config.AppSpec(id="", name="", version="1.0.0", summary=""))
        self.formats.set_formats(["deb", "rpm"])
        self.output.set_path(Path.cwd() / "dist")
        self.log.clear()
        self._update_title()

    def ask_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Ouvrir une configuration", str(self._base_dir()), TOML_FILTER)
        if path:
            self.open_config(Path(path))

    def open_config(self, path: Path) -> None:
        try:
            spec = config.load(path)
        except ConfigError as e:
            QMessageBox.critical(self, "Configuration invalide", str(e))
            return
        self.config_path = path.resolve()
        self.form.set_spec(spec)
        self.formats.set_formats(spec.formats)
        self.output.set_path(spec.output_dir)
        self._update_title()

    def save(self) -> bool:
        if not self.config_path:
            return self.save_as()
        config.save(self.current_spec(), self.config_path)
        self.statusBar().showMessage(f"Enregistré : {self.config_path}", 4000)
        return True

    def save_as(self) -> bool:
        start = str(self._base_dir() / config.CONFIG_NAME)
        path, _ = QFileDialog.getSaveFileName(self, "Enregistrer la configuration", start, TOML_FILTER)
        if not path:
            return False
        self.config_path = Path(path).resolve()
        self._update_title()
        return self.save()

    # ---- build ------------------------------------------------------------------
    def start_build(self) -> None:
        spec = self.current_spec()
        formats = self.formats.buildable_formats()
        if not formats:
            QMessageBox.warning(self, "Aucun format", "Cochez au moins un format disponible sur cette machine.")
            return
        # Only the platforms being built need their files (e.g. no .exe for a deb).
        # Files a build command will produce are checked by core.build, after running it.
        platforms = sorted({BACKENDS[f].platform for f in formats})
        problems = spec.validate(check_files=False, platforms=platforms)
        if problems:
            QMessageBox.warning(self, "Informations manquantes", "\n".join(f"• {p}" for p in problems))
            return
        self.log.clear()
        self.build_button.setEnabled(False)
        self.build_button.setText("Construction en cours…")
        self.worker = BuildWorker(spec, formats, self)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.done.connect(self._build_done)
        self.worker.failed.connect(self._build_failed)
        self.worker.finished.connect(self._build_finished)
        self.worker.start()

    def _build_done(self, result) -> None:
        lines = [f"✔ {name} : {p.name}" for name, paths in result.packages.items() for p in paths]
        lines += [f"✘ {name} : {err}" for name, err in result.errors.items()]
        self.log.appendPlainText("\n" + "\n".join(lines))
        if result.ok:
            self.statusBar().showMessage("Paquets construits avec succès.", 8000)
        else:
            QMessageBox.warning(self, "Construction partielle", "\n".join(lines))

    def _build_failed(self, message: str) -> None:
        self.log.appendPlainText(f"\nERREUR : {message}")
        QMessageBox.critical(self, "Échec de la construction", message)

    def _build_finished(self) -> None:
        self.build_button.setEnabled(True)
        self.build_button.setText("Construire les paquets")
        self.worker = None

    def open_output(self) -> None:
        path = self.output.path()
        if path and path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.statusBar().showMessage("Le dossier de sortie n'existe pas encore.", 4000)

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Construction en cours", "Attendez la fin de la construction.")
            event.ignore()
            return
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("PackagingOnLinux")
    app.setDesktopFileName("io.github.spatulox.PackagingOnLinux")
    window = MainWindow(Path(argv[0]) if argv else None)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
