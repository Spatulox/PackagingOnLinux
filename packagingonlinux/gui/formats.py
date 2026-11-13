from __future__ import annotations

from packagingonlinux import container, core
from packagingonlinux.gui.qt import QCheckBox, QGridLayout, QGroupBox, QLabel


PLATFORM_TITLES = {"linux": "Linux", "windows": "Windows"}
CONTAINER_TIP = ("Construit les formats Linux (et lance la commande de build Linux) dans un conteneur "
                 "Docker, qui a tous les outils : c'est ce qui permet de les construire depuis Windows. "
                 "Il faut Docker Desktop (ou Docker Engine sous Linux) installé et démarré. "
                 "Le conteneur ne voit que le dossier de la configuration et le dossier de sortie.")
UNSUPPORTED_IN_CONTAINER = ("snapcraft n'est distribué qu'en snap : construisez ce format sous Linux "
                            "avec snapcraft, ou en CI.")


class FormatsPanel(QGroupBox):
    """One checkbox per backend, grouped by platform, plus the "build in a Docker container"
    option for the Linux formats. Formats that can't be built (missing tools, or no
    container support) are disabled, with a hint."""

    def __init__(self, parent=None):
        super().__init__("Formats à générer", parent)
        self.checkboxes: dict[str, QCheckBox] = {}
        self.notes: dict[str, QLabel] = {}
        self.status: dict[str, core.ToolStatus] = {}
        self.headers: dict[str, QLabel] = {}
        self.container = QCheckBox("Construire dans un conteneur Docker")
        self.container.setToolTip(CONTAINER_TIP)
        self.container.setChecked(container.default_enabled())
        grid = QGridLayout(self)
        row = 0
        for status in core.doctor():
            if status.platform not in self.headers:
                header = QLabel(f"<b>{PLATFORM_TITLES.get(status.platform, status.platform)}</b>")
                self.headers[status.platform] = header
                grid.addWidget(header, row, 0, 1, 2)
                row += 1
                if status.platform == "linux":
                    grid.addWidget(self.container, row, 0, 1, 2)
                    row += 1
            box = QCheckBox(status.label)
            self.checkboxes[status.name] = box
            self.notes[status.name] = QLabel()
            self.status[status.name] = status
            grid.addWidget(box, row, 0)
            grid.addWidget(self.notes[status.name], row, 1)
            row += 1
        grid.setColumnStretch(1, 1)
        self.container.toggled.connect(self._update_availability)
        self._update_availability()

    def use_container(self) -> bool:
        return self.container.isChecked()

    def _in_container(self, name: str) -> bool:
        return self.status[name].platform == "linux" and self.use_container()

    def unavailable_reason(self, name: str) -> str | None:
        """Why format `name` can't be built with the current options (None: it can)."""
        if self._in_container(name):
            return "impossible dans le conteneur Docker" if name in container.UNSUPPORTED else None
        status = self.status[name]
        return None if status.ok else f"outil(s) manquant(s) : {', '.join(status.missing)}"

    def available(self, name: str) -> bool:
        return self.unavailable_reason(name) is None

    def _update_availability(self) -> None:
        for name, box in self.checkboxes.items():
            status = self.status[name]
            reason = self.unavailable_reason(name)
            note = ""
            if reason is None:
                tip = ("Construit dans le conteneur Docker" if self._in_container(name)
                       else f"Outils présents pour « {name} »")
            elif self._in_container(name):
                note, tip = "⚠ impossible en conteneur", UNSUPPORTED_IN_CONTAINER
            else:
                missing = ", ".join(status.missing)
                note = f"⚠ manque : {missing}"
                tip = f"Outil(s) manquant(s) : {missing}\nInstallation : {status.install_hint}"
            box.setEnabled(reason is None)
            box.setToolTip(tip)
            self.notes[name].setText(note)
            self.notes[name].setToolTip(tip)

    def set_formats(self, formats: list[str]) -> None:
        for name, box in self.checkboxes.items():
            box.setChecked(name in formats)

    def formats(self) -> list[str]:
        """All formats ticked in the config, including unavailable ones (kept when saving)."""
        return [n for n, b in self.checkboxes.items() if b.isChecked()]

    def buildable_formats(self) -> list[str]:
        return [n for n in self.formats() if self.available(n)]
