"""Qt binding shim: PySide6 if installed (pip extra), else PyQt6 (packaged by distros).

The rest of the GUI imports Qt names from here only. Use fully scoped enums
(Qt.AlignmentFlag.AlignCenter, not Qt.AlignCenter): PyQt6 rejects the short form.
"""

# ruff: noqa: F401, F403
try:
    from PySide6.QtCore import *
    from PySide6.QtGui import *
    from PySide6.QtWidgets import *
    from PySide6.QtCore import Signal

    API = "PySide6"
except ImportError:
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import pyqtSignal as Signal

    API = "PyQt6"
