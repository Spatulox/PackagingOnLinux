"""Entry point of the Windows build (PyInstaller), the counterpart of packaging/packagingonlinux.

With no arguments (Start menu shortcut) it opens the GUI; otherwise it behaves like the CLI.
"""

import sys

from packagingonlinux.cli import main

raise SystemExit(main(sys.argv[1:] or ["gui"]))
