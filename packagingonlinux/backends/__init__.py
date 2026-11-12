"""Registry of packaging backends. Order = display order in the CLI and the GUI."""

from packagingonlinux.backends.base import Backend, BuildContext
from packagingonlinux.backends.deb import DebBackend
from packagingonlinux.backends.rpm import RpmBackend
from packagingonlinux.backends.tarball import TarballBackend

BACKENDS: dict[str, Backend] = {b.name: b for b in (DebBackend(), RpmBackend(), TarballBackend())}

__all__ = ["BACKENDS", "Backend", "BuildContext"]
