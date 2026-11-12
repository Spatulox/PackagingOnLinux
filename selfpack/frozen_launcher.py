"""Entry point of the PyInstaller builds: the Windows .exe, and the Linux bundle packaged as
AppImage, Flatpak and Snap (see selfpack/linux/bundled_config.py). It is the counterpart
of selfpack/linux/launcher, which runs on the system's Python (deb, rpm, tar.gz).

With no arguments (desktop menu, Start menu shortcut) it opens the GUI; otherwise it
behaves like the CLI.
"""

import sys

from packagingonlinux.cli import main

raise SystemExit(main(sys.argv[1:] or ["gui"]))
