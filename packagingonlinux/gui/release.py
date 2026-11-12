"""Dialog shown before a build: which kind of release it is, i.e. how to bump the version,
and whether it is a final release or an alpha, beta or release candidate."""

from __future__ import annotations

from packagingonlinux.gui.qt import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QRadioButton, QSpinBox, QVBoxLayout,
)
from packagingonlinux.version import FINAL, KEEP, bump, next_version, split

CHOICES = [
    ("fix", "Correctif (fix)"),
    ("minor", "Mineure (minor)"),
    ("major", "Majeure (major)"),
]
STAGE_LABELS = [
    (FINAL, "Finale (release)"),
    ("rc", "Release candidate (rc)"),
    ("beta", "Bêta (beta)"),
    ("alpha", "Alpha (alpha)"),
]


class ReleaseDialog(QDialog):
    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        self.current = version
        self.current_base, self.current_stage, self.current_number = split(version)
        self.setWindowTitle("Type de release")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Version actuelle : <b>{version}</b><br>Quel type de release construire ?"))
        self.buttons: dict[str, QRadioButton] = {}
        for key, label in CHOICES:
            self.buttons[key] = QRadioButton(f"{label} : {version} → {bump(version, key)}")
        self.buttons[KEEP] = QRadioButton(f"Aucune : garder les numéros {self.current_base}")
        for button in self.buttons.values():
            layout.addWidget(button)

        self.stage = QComboBox()
        for key, label in STAGE_LABELS:
            self.stage.addItem(label, key)
        self.stage.setCurrentIndex(self.stage.findData(self.current_stage))
        self.number = QSpinBox()
        self.number.setRange(1, 999)
        self.number.setPrefix("n° ")
        stage_row = QHBoxLayout()
        stage_row.addWidget(QLabel("Étape :"))
        stage_row.addWidget(self.stage, 1)
        stage_row.addWidget(self.number)
        layout.addLayout(stage_row)
        self.result = QLabel()
        layout.addWidget(self.result)

        # From a pre-release, the likely next build is the next one of the same stage
        # (rc1 -> rc2); from a final release, the next fix.
        self.buttons[KEEP if self.current_stage != FINAL else "fix"].setChecked(True)
        self._reset_number()
        for button in self.buttons.values():
            button.toggled.connect(self._reset_number)
        self.stage.currentIndexChanged.connect(self._reset_number)
        self.number.valueChanged.connect(self._update_result)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("Construire")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def choice(self) -> str:
        return next(key for key, button in self.buttons.items() if button.isChecked())

    def stage_choice(self) -> str:
        return self.stage.currentData()

    def version(self) -> str:
        return next_version(self.current, self.choice(), self.stage_choice(), self.number.value())

    def _reset_number(self) -> None:
        """Next number of the current stage when keeping the numbers, else 1."""
        same = self.choice() == KEEP and self.stage_choice() == self.current_stage
        self.number.blockSignals(True)
        self.number.setValue(self.current_number + 1 if same and self.current_stage != FINAL else 1)
        self.number.blockSignals(False)
        self.number.setEnabled(self.stage_choice() != FINAL)
        self._update_result()

    def _update_result(self) -> None:
        version = self.version()
        note = " (inchangée : simple reconstruction)" if version == self.current else ""
        self.result.setText(f"Version construite : <b>{version}</b>{note}")


def ask_release(parent, version: str) -> str | None:
    """The version to build, or None if the user cancelled."""
    dialog = ReleaseDialog(version, parent)
    return dialog.version() if dialog.exec() else None
