from __future__ import annotations

from compileonlinux import core
from compileonlinux.config import AppSpec
from compileonlinux.gui.qt import QThread, Signal


class BuildWorker(QThread):
    """Runs core.build off the UI thread and streams its log lines."""

    log = Signal(str)
    done = Signal(object)    # core.BuildResult
    failed = Signal(str)

    def __init__(self, spec: AppSpec, formats: list[str], parent=None):
        super().__init__(parent)
        self.spec = spec
        self.formats = formats

    def run(self) -> None:
        try:
            result = core.build(self.spec, self.formats, log=self.log.emit)
        except Exception as e:  # surfaced in the UI instead of killing the thread silently
            self.failed.emit(str(e))
        else:
            self.done.emit(result)
