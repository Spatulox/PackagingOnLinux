"""Recently opened configurations, kept with QSettings (on Linux:
~/.config/PackagingOnLinux/PackagingOnLinux.conf), most recent first."""

from __future__ import annotations

from pathlib import Path

from packagingonlinux.gui.qt import QSettings

MAX_RECENT = 10
KEY = "recentFiles"


def default_settings() -> QSettings:
    return QSettings("PackagingOnLinux", "PackagingOnLinux")


class RecentFiles:
    def __init__(self, settings: QSettings):
        self.settings = settings

    def paths(self) -> list[Path]:
        value = self.settings.value(KEY)
        if not value:
            return []
        if isinstance(value, str):  # an INI list of one item reads back as a plain string
            value = [value]
        return [Path(v) for v in value if v]

    def add(self, path: Path) -> None:
        path = Path(path).resolve()
        self._store([path] + [p for p in self.paths() if p != path])

    def clear(self) -> None:
        self._store([])

    def _store(self, paths: list[Path]) -> None:
        if paths:
            self.settings.setValue(KEY, [str(p) for p in paths[:MAX_RECENT]])
        else:
            self.settings.remove(KEY)
        self.settings.sync()
