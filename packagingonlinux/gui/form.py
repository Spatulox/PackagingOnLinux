from __future__ import annotations

from pathlib import Path

from packagingonlinux.linux import elf
from packagingonlinux.windows import pe
from packagingonlinux.config import COMMON_LICENSES, MAIN_CATEGORIES, AppSpec, Target, suggest_id
from packagingonlinux.gui.qt import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPixmap, QPlainTextEdit, QPushButton, Qt, QTabWidget, QVBoxLayout, QWidget, Signal,
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


class TargetWidget(QWidget):
    """What to package for one platform: build command, executable (or folder) and icon."""

    changed = Signal()

    def __init__(self, platform: str, parent=None):
        super().__init__(parent)
        self.platform = platform
        windows = platform == "windows"
        self.mode = QComboBox()
        self.mode.addItems(["Un seul exécutable", "Un dossier (exécutable + fichiers)"])
        self.binary = PathField("Choisir l'exécutable",
                                file_filter="Exécutables Windows (*.exe);;Tous les fichiers (*)" if windows else "")
        self.dir = PathField("Choisir le dossier de l'application", directory=True)
        self.exec = QLineEdit()
        self.exec.setPlaceholderText("chemin de l'exécutable dans le dossier, ex. "
                                     + ("MonApp.exe" if windows else "bin/monapp"))
        self.arch = QLabel("—")
        self.icon = PathField("Choisir l'icône",
                              file_filter="Images (*.ico *.png)" if windows else "Images (*.png *.svg)")
        if windows:
            self.icon.edit.setPlaceholderText("optionnelle : .ico, ou PNG carré ≤ 256 px ; sinon l'icône Linux")
        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(64, 64)
        self.icon_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.command = QLineEdit()
        self.command.setPlaceholderText(
            "optionnel, ex. wails build -platform windows/amd64" if windows
            else "optionnel, ex. wails build  (lancé avant le packaging)")
        self.command.setToolTip(
            f"Lancée dans le dossier de la configuration avant le packaging,\n"
            f"seulement si un format {'Windows' if windows else 'Linux'} est construit.\n"
            "Variables disponibles : $APP_VERSION, $APP_NAME, $APP_ID, $APP_PLATFORM\n"
            'ex. go build -ldflags "-X main.version=$APP_VERSION"'
        )

        self._form = QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.addRow("Type", self.mode)
        self._form.addRow("Exécutable", self.binary)
        self._form.addRow("Dossier", self.dir)
        self._form.addRow("Exécutable dans le dossier", self.exec)
        self._form.addRow("Architecture", self.arch)
        icon_row = QHBoxLayout()
        icon_row.addWidget(self.icon, 1)
        icon_row.addWidget(self.icon_preview)
        self._form.addRow("Icône", icon_row)
        self._form.addRow("Commande de compilation", self.command)

        self.mode.currentIndexChanged.connect(self._update_mode)
        self.binary.changed.connect(self._update_arch)
        self.dir.changed.connect(self._update_arch)
        self.exec.textChanged.connect(self._update_arch)
        self.icon.changed.connect(self._update_icon)
        for signal in (self.binary.changed, self.dir.changed, self.exec.textChanged):
            signal.connect(self.changed)
        self._update_mode()

    def is_dir_mode(self) -> bool:
        return self.mode.currentIndex() == 1

    def _update_mode(self) -> None:
        dir_mode = self.is_dir_mode()
        self._form.setRowVisible(self.binary, not dir_mode)
        self._form.setRowVisible(self.dir, dir_mode)
        self._form.setRowVisible(self.exec, dir_mode)
        self._update_arch()

    def executable(self) -> Path | None:
        if self.is_dir_mode():
            d = self.dir.path()
            return d / self.exec.text().strip() if d and self.exec.text().strip() else None
        return self.binary.path()

    def _update_arch(self) -> None:
        exe = self.executable()
        if not exe or not exe.is_file():
            self.arch.setText("—")
            return
        try:
            if self.platform == "windows":
                label = pe.detect_arch(exe)
            else:
                deb, rpm = elf.detect_arch(exe)
                label = "indépendante (script)" if deb == "all" else f"{deb} / {rpm}"
        except ValueError as e:
            self.arch.setText(f"⚠ {e}")
            return
        self.arch.setText(label)

    def _update_icon(self) -> None:
        path = self.icon.path()
        pixmap = QPixmap(str(path)) if path and path.is_file() else QPixmap()
        if pixmap.isNull():
            self.icon_preview.clear()
            return
        self.icon_preview.setPixmap(pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.icon_preview.setToolTip(f"{pixmap.width()}×{pixmap.height()} px")

    def set_target(self, target: Target | None) -> None:
        target = target or Target()
        self.mode.setCurrentIndex(1 if target.dir else 0)
        self.binary.set_path(target.binary)
        self.dir.set_path(target.dir)
        self.exec.setText(target.exec)
        self.icon.set_path(target.icon)
        self.command.setText(target.command)

    def target(self) -> Target | None:
        """The edited target, or None when every field is empty (= no section for this platform)."""
        dir_mode = self.is_dir_mode()
        target = Target(
            binary=None if dir_mode else self.binary.path(),
            dir=self.dir.path() if dir_mode else None,
            exec=self.exec.text().strip() if dir_mode else "",
            icon=self.icon.path(),
            command=self.command.text().strip(),
        )
        return None if target == Target() else target


class AppForm(QWidget):
    """Edits every AppSpec field except formats/output (see FormatsPanel and the main window).

    The files to package are edited per platform, in a Linux and a Windows tab."""

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
        self.license = QComboBox()
        self.license.addItems(COMMON_LICENSES)
        self.license.setEditable(True)
        self.license.setCurrentText("LicenseRef-proprietary")
        self.license.setToolTip(
            "Choisissez une licence ou tapez un autre identifiant SPDX\n"
            "(liste complète : https://spdx.org/licenses/), ex. GPL-3.0-only OR MIT"
        )
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

        # --- files, per platform
        self.linux = TargetWidget("linux")
        self.windows = TargetWidget("windows")

        # --- dependencies (Linux only)
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

        linux_tab = QWidget()
        linux_layout = QVBoxLayout(linux_tab)
        linux_layout.addWidget(self.linux)
        linux_layout.addWidget(deps)
        windows_tab = QWidget()
        windows_layout = QVBoxLayout(windows_tab)
        hint = QLabel(
            "Optionnel. Un exécutable Linux ne tourne pas sous Windows : indiquez le .exe "
            "Windows, ou la commande qui le produit depuis Linux "
            "(ex. wails build -platform windows/amd64, GOOS=windows go build).")
        hint.setWordWrap(True)
        windows_layout.addWidget(hint)
        windows_layout.addWidget(self.windows)
        windows_layout.addStretch(1)
        self.platform_tabs = QTabWidget()
        self.platform_tabs.addTab(linux_tab, "Linux")
        self.platform_tabs.addTab(windows_tab, "Windows")
        files = QGroupBox("Fichiers à empaqueter")
        QVBoxLayout(files).addWidget(self.platform_tabs)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(meta)
        layout.addWidget(files)

        self.name.textChanged.connect(self._suggest_id)
        self.maintainer.textChanged.connect(self._suggest_id)
        self.app_id.textEdited.connect(lambda _: setattr(self, "_id_auto", False))
        self.linux.changed.connect(self._suggest_name)
        self.windows.changed.connect(self._suggest_name)

    # ---- reactive helpers ---------------------------------------------------
    def _suggest_id(self) -> None:
        if self._id_auto and self.name.text().strip():
            self.app_id.setText(suggest_id(self.name.text(), self.maintainer.text()))

    def _suggest_name(self) -> None:
        if self.name.text().strip():
            return
        for target in (self.linux, self.windows):
            exe = target.binary.path()
            if exe and not target.is_dir_mode():
                self.name.setText(exe.stem if target.platform == "windows" else exe.name)
                return

    # ---- AppSpec <-> widgets --------------------------------------------------
    def set_spec(self, spec: AppSpec) -> None:
        self._id_auto = False
        self.name.setText(spec.name)
        self.app_id.setText(spec.id)
        self.version.setText(spec.version)
        self.summary.setText(spec.summary)
        self.description.setPlainText(spec.description)
        self.maintainer.setText(spec.maintainer)
        self.license.setCurrentText(spec.license)
        self.homepage.setText(spec.homepage)
        self.category.setCurrentText(spec.categories[0] if spec.categories else "Utility")
        self.linux.set_target(spec.linux)
        self.windows.set_target(spec.windows)
        self.deps_auto.setChecked(spec.deps_auto)
        self.deps_deb.setText(", ".join(spec.deps_deb))
        self.deps_rpm.setText(", ".join(spec.deps_rpm))
        self._id_auto = not spec.id

    def to_spec(self, base_dir: Path, formats: list[str], output_dir: Path) -> AppSpec:
        category = self.category.currentText().strip()
        return AppSpec(
            id=self.app_id.text().strip(),
            name=self.name.text().strip(),
            version=self.version.text().strip(),
            summary=self.summary.text().strip(),
            description=self.description.toPlainText().strip(),
            license=self.license.currentText().strip() or "LicenseRef-proprietary",
            maintainer=self.maintainer.text().strip(),
            homepage=self.homepage.text().strip(),
            categories=[category] if category else ["Utility"],
            linux=self.linux.target(),
            windows=self.windows.target(),
            deps_auto=self.deps_auto.isChecked(),
            deps_deb=_split(self.deps_deb.text()),
            deps_rpm=_split(self.deps_rpm.text()),
            formats=formats,
            output_dir=output_dir,
            base_dir=base_dir,
        )
