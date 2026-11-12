from __future__ import annotations

from packagingonlinux import core
from packagingonlinux.gui.qt import QCheckBox, QGridLayout, QGroupBox, QLabel


PLATFORM_TITLES = {"linux": "Linux", "windows": "Windows (depuis Linux)"}


class FormatsPanel(QGroupBox):
    """One checkbox per backend, grouped by platform. Backends whose tools are missing are
    disabled, with a hint."""

    def __init__(self, parent=None):
        super().__init__("Formats à générer", parent)
        self.checkboxes: dict[str, QCheckBox] = {}
        self.status: dict[str, core.ToolStatus] = {}
        self.headers: dict[str, QLabel] = {}
        grid = QGridLayout(self)
        row = 0
        for status in core.doctor():
            if status.platform not in self.headers:
                header = QLabel(f"<b>{PLATFORM_TITLES.get(status.platform, status.platform)}</b>")
                self.headers[status.platform] = header
                grid.addWidget(header, row, 0, 1, 2)
                row += 1
            box = QCheckBox(status.label)
            note = QLabel()
            if status.ok:
                box.setToolTip(f"Outils présents pour « {status.name} »")
            else:
                box.setEnabled(False)
                missing = ", ".join(status.missing)
                note.setText(f"⚠ manque : {missing}")
                tip = f"Outil(s) manquant(s) : {missing}\nInstallation : {status.install_hint}"
                box.setToolTip(tip)
                note.setToolTip(tip)
            self.checkboxes[status.name] = box
            self.status[status.name] = status
            grid.addWidget(box, row, 0)
            grid.addWidget(note, row, 1)
            row += 1
        grid.setColumnStretch(1, 1)

    def set_formats(self, formats: list[str]) -> None:
        for name, box in self.checkboxes.items():
            box.setChecked(name in formats)

    def formats(self) -> list[str]:
        """All formats ticked in the config, including unavailable ones (kept when saving)."""
        return [n for n, b in self.checkboxes.items() if b.isChecked()]

    def buildable_formats(self) -> list[str]:
        return [n for n in self.formats() if self.status[n].ok]
