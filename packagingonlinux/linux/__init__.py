"""Linux: ELF reading, dependency detection, the FHS staging tree and the deb/rpm/tar.gz backends.

No imports here: config imports linux.elf, and importing the backends from this file would
import config back while it is still loading. The backends are registered in core.BACKENDS.
"""
