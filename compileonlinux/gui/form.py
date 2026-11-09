from __future__ import annotations

from pathlib import Path

from compileonlinux import elf
from compileonlinux.config import MAIN_CATEGORIES, AppSpec, suggest_id
from compileonlinux.gui.qt import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPixmap, QPlainTextEdit, QPushButton, Qt, QVBoxLayout, QWidget, Signal,
)


class PathField(QWidget):
    changed = Signal(str)

    def __init__(self, title: str, directory: bool = False, file_filter: str = "", parent=None):
        super().__init__(parent)
        self.title = title
        self.directory = directory
        self.file_filter = file_filter
        self.edit = QLineEdit()
        button = QPushButton("Parcourir…")
        button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)
        self.edit.textChanged.connect(self.changed)

    def _browse(self) -> None:
        start = self.edit.text() or str(Path.cwd())
        if self.directory:
            path = QFileDialog.getExistingDirectory(self, self.title, start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, self.title, start, self.file_filter)
        if path:
            self.edit.setText(path)

    def path(self) -> Path | None:
        text = self.edit.text().strip()
        return Path(text).expanduser().resolve() if text else None

    def set_path(self, path: Path | None) -> None:
        self.edit.setText(str(path) if path else "")


def _split(text: str) -> list[str]:
    return [p.strip() for p in text.split(",") if p.strip()]


class AppForm(QWidget):
    """Edits every AppSpec field except formats/output (see FormatsPanel and the main window)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._id_auto = True

        # --- application metadata
        self.name = QLineEdit()
        self.app_id = QLineEdit()
        self.app_id.setPlaceholderText("io.github.vous.MonApp")
        self.version = QLineEdit("1.0.0")
        self.summary = QLineEdit()
        self.summary.setPlaceholderText("Une phrase qui décrit l'application")
        self.description = QPlainTextEdit()
        self.description.setPlaceholderText("Description longue (optionnelle). Paragraphes séparés par une ligne vide.")
        self.description.setFixedHeight(70)
        self.maintainer = QLineEdit()
        self.maintainer.setPlaceholderText("Prénom Nom <email@exemple.fr>")
        self.license = QLineEdit("LicenseRef-proprietary")
        self.license.setToolTip("Identifiant SPDX, ex. MIT, GPL-3.0-only, Apache-2.0")
        self.homepage = QLineEdit()
        self.category = QComboBox()
        self.category.addItems(MAIN_CATEGORIES)
        self.category.setEditable(True)
        self.category.setCurrentText("Utility")

        meta = QGroupBox("Application")
        f = QFormLayout(meta)
        f.addRow("Nom", self.name)
        f.addRow("Identifiant", self.app_id)
        f.addRow("Version", self.version)
        f.addRow("Résumé", self.summary)
        f.addRow("Description", self.description)
        f.addRow("Mainteneur", self.maintainer)
        f.addRow("Licence", self.license)
        f.addRow("Site web", self.homepage)
        f.addRow("Catégorie", self.category)

        # --- files
        self.mode = QComboBox()
        self.mode.addItems(["Un seul exécutable", "Un dossier (exécutable + fichiers)"])
        self.binary = PathField("Choisir l'exécutable")
        self.dir = PathField("Choisir le dossier de l'application", directory=True)
        self.exec = QLineEdit()
        self.exec.setPlaceholderText("chemin de l'exécutable dans le dossier, ex. bin/monapp")
        self.arch = QLabel("—")
        self.icon = PathField("Choisir l'icône", file_filter="Images (*.png *.svg)")
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(64, 64)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.build_command = QLineEdit()
        self.build_command.setPlaceholderText("optionnel, ex. wails build  (lancé avant le packaging)")
        self.build_command.setToolTip(
            "Lancée dans le dossier de la configuration avant le packaging.\n"
            "Variables disponibles : $APP_VERSION, $APP_NAME, $APP_ID\n"
            'ex. go build -ldflags "-X main.version=$APP_VERSION"'
        )

        files = QGroupBox("Fichiers")
        self._files_form = QFormLayout(files)
        self._files_form.addRow("Type", self.mode)
        self._files_form.addRow("Exécutable", self.binary)
        self._files_form.addRow("Dossier", self.dir)
        self._files_form.addRow("Exécutable dans le dossier", self.exec)
        self._files_form.addRow("Architecture", self.arch)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon, 1)
        icon_row.addWidget(self.icon_preview)
        self._files_form.addRow("Icône", icon_row)
        self._files_form.addRow("Commande de compilation", self.build_command)

        # --- dependencies
        self.deps_auto = QCheckBox("Détecter automatiquement les bibliothèques nécessaires")
        self.deps_auto.setChecked(True)
        self.deps_deb = QLineEdit()
        self.deps_deb.setPlaceholderText("ex. libgtk-3-0, libwebkit2gtk-4.1-0")
        self.deps_rpm = QLineEdit()
        self.deps_rpm.setPlaceholderText("ex. gtk3, webkit2gtk4.1")
        deps = QGroupBox("Dépendances")
        d = QFormLayout(deps)
        d.addRow(self.deps_auto)
        d.addRow("En plus (deb)", self.deps_deb)
        d.addRow("En plus (rpm)", self.deps_rpm)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(meta)
        layout.addWidget(files)
        layout.addWidget(deps)

        self.name.textChanged.connect(self._suggest_id)
        self.maintainer.textChanged.connect(self._suggest_id)
        self.app_id.textEdited.connect(lambda _: setattr(self, "_id_auto", False))
        self.mode.currentIndexChanged.connect(self._update_mode)
        self.binary.changed.connect(self._update_arch)
        self.binary.changed.connect(self._suggest_name)
        self.dir.changed.connect(self._update_arch)
        self.exec.textChanged.connect(self._update_arch)
        self.icon.changed.connect(self._update_icon)
        self._update_mode()

    # ---- reactive helpers ---------------------------------------------------
    def _suggest_id(self) -> None:
        if self._id_auto and self.name.text().strip():
            self.app_id.setText(suggest_id(self.name.text(), self.maintainer.text()))

    def _suggest_name(self) -> None:
        if not self.name.text().strip() and self.binary.path():
            self.name.setText(self.binary.path().name)

    def _is_dir_mode(self) -> bool:
        return self.mode.currentIndex() == 1

    def _update_mode(self) -> None:
        dir_mode = self._is_dir_mode()
        self._files_form.setRowVisible(self.binary, not dir_mode)
        self._files_form.setRowVisible(self.dir, dir_mode)
        self._files_form.setRowVisible(self.exec, dir_mode)
        self._update_arch()

    def _executable(self) -> Path | None:
        if self._is_dir_mode():
            d = self.dir.path()
            return d / self.exec.text().strip() if d and self.exec.text().strip() else None
        return self.binary.path()

    def _update_arch(self) -> None:
        exe = self._executable()
        if not exe or not exe.is_file():
            self.arch.setText("—")
            return
        try:
            deb, rpm = elf.detect_arch(exe)
        except ValueError as e:
            self.arch.setText(f"⚠ {e}")
            return
        label = "indépendante (script)" if deb == "all" else f"{deb} / {rpm}"
        self.arch.setText(label)

    def _update_icon(self) -> None:
        path = self.icon.path()
        pixmap = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        if pixmap.isNull():
            self.icon_preview.clear()
            return
        self.icon_preview.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.icon_preview.setToolTip(f"{pixmap.width()}×{pixmap.height()} px")

    # ---- AppSpec <-> widgets --------------------------------------------------
    def set_spec(self, spec: AppSpec) -> None:
        self._id_auto = False
        self.name.setText(spec.name)
        self.app_id.setText(spec.id)
        self.version.setText(spec.version)
        self.summary.setText(spec.summary)
        self.description.setPlainText(spec.description)
        self.maintainer.setText(spec.maintainer)
        self.license.setText(spec.license)
        self.homepage.setText(spec.homepage)
        self.category.setCurrentText(spec.categories[0] if spec.categories else "Utility")
        self.mode.setCurrentIndex(1 if spec.dir else 0)
        self.binary.set_path(spec.binary)
        self.dir.set_path(spec.dir)
        self.exec.setText(spec.exec)
        self.icon.set_path(spec.icon)
        self.build_command.setText(spec.build_command)
        self.deps_auto.setChecked(spec.deps_auto)
        self.deps_deb.setText(", ".join(spec.deps_deb))
        self.deps_rpm.setText(", ".join(spec.deps_rpm))
        self._id_auto = not spec.id

    def to_spec(self, base_dir: Path, formats: list[str], output_dir: Path) -> AppSpec:
        dir_mode = self._is_dir_mode()
        category = self.category.currentText().strip()
        return AppSpec(
            id=self.app_id.text().strip(),
            name=self.name.text().strip(),
            version=self.version.text().strip(),
            summary=self.summary.text().strip(),
            description=self.description.toPlainText().strip(),
            license=self.license.text().strip() or "LicenseRef-proprietary",
            maintainer=self.maintainer.text().strip(),
            homepage=self.homepage.text().strip(),
            categories=[category] if category else ["Utility"],
            binary=None if dir_mode else self.binary.path(),
            dir=self.dir.path() if dir_mode else None,
            exec=self.exec.text().strip() if dir_mode else "",
            icon=self.icon.path(),
            build_command=self.build_command.text().strip(),
            deps_auto=self.deps_auto.isChecked(),
            deps_deb=_split(self.deps_deb.text()),
            deps_rpm=_split(self.deps_rpm.text()),
            formats=formats,
            output_dir=output_dir,
            base_dir=base_dir,
        )
