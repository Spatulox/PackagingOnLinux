from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox, QLabel

from compileonlinux import core


class FormatsPanel(QGroupBox):
    """One checkbox per backend. Backends whose tools are missing are disabled, with a hint."""

    def __init__(self, parent=None):
        super().__init__("Formats à générer", parent)
        self.checkboxes: dict[str, QCheckBox] = {}
        self.status: dict[str, core.ToolStatus] = {}
        grid = QGridLayout(self)
        for row, status in enumerate(core.doctor()):
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
        grid.setColumnStretch(1, 1)

    def set_formats(self, formats: list[str]) -> None:
        for name, box in self.checkboxes.items():
            box.setChecked(name in formats)

    def formats(self) -> list[str]:
        """All formats ticked in the config, including unavailable ones (kept when saving)."""
        return [n for n, b in self.checkboxes.items() if b.isChecked()]

    def buildable_formats(self) -> list[str]:
        return [n for n in self.formats() if self.status[n].ok]
