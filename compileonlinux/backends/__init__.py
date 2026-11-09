"""Registry of packaging backends. Order = display order in the CLI and the GUI."""

from compileonlinux.backends.base import Backend, BuildContext
from compileonlinux.backends.deb import DebBackend
from compileonlinux.backends.rpm import RpmBackend
from compileonlinux.backends.tarball import TarballBackend

BACKENDS: dict[str, Backend] = {b.name: b for b in (DebBackend(), RpmBackend(), TarballBackend())}

__all__ = ["BACKENDS", "Backend", "BuildContext"]
