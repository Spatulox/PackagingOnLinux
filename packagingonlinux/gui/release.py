"""Dialog shown before a build: which kind of release it is, i.e. how to bump the version."""

from __future__ import annotations

from packagingonlinux.gui.qt import QDialog, QDialogButtonBox, QLabel, QRadioButton, QVBoxLayout
from packagingonlinux.version import bump

KEEP = "keep"
CHOICES = [
    ("fix", "Correctif (fix)"),
    ("minor", "Mineure (minor)"),
    ("major", "Majeure (major)"),
]


class ReleaseDialog(QDialog):
    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Type de release")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Version actuelle : <b>{version}</b><br>Quel type de release construire ?"))
        self.buttons: dict[str, QRadioButton] = {}
        for key, label in CHOICES:
            self.buttons[key] = QRadioButton(f"{label} : {version} → {bump(version, key)}")
        self.buttons[KEEP] = QRadioButton(f"Aucune : reconstruire la {version} sans changer de version")
        for button in self.buttons.values():
            layout.addWidget(button)
        self.buttons["fix"].setChecked(True)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("Construire")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def choice(self) -> str:
        return next(key for key, button in self.buttons.items() if button.isChecked())


def ask_release(parent, version: str) -> str | None:
    """"fix", "minor", "major", KEEP, or None if the user cancelled."""
    dialog = ReleaseDialog(version, parent)
    return dialog.choice() if dialog.exec() else None
