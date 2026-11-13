from __future__ import annotations

from packagingonlinux import core
from packagingonlinux.config import AppSpec
from packagingonlinux.gui.qt import QThread, Signal


class BuildWorker(QThread):
    """Runs core.build off the UI thread and streams its log lines."""

    log = Signal(str)
    done = Signal(object)    # core.BuildResult
    failed = Signal(str)

    def __init__(self, spec: AppSpec, formats: list[str], container: bool = False, parent=None):
        super().__init__(parent)
        self.spec = spec
        self.formats = formats
        self.container = container  # build the Linux formats in a Docker container

    def run(self) -> None:
        try:
            result = core.build(self.spec, self.formats, log=self.log.emit, container=self.container)
        except Exception as e:  # surfaced in the UI instead of killing the thread silently
            self.failed.emit(str(e))
        else:
            self.done.emit(result)
