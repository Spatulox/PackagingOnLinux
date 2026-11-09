from __future__ import annotations

import tarfile
from pathlib import Path

from compileonlinux.backends.base import Backend, BuildContext


class TarballBackend(Backend):
    name = "tarball"
    label = "tar.gz"

    def build(self, ctx: BuildContext) -> list[Path]:
        spec = ctx.spec
        out = ctx.outdir / f"{spec.package_name}-{spec.version}-{spec.arch[1]}.tar.gz"

        def root_owned(info: tarfile.TarInfo) -> tarfile.TarInfo:
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            return info

        with tarfile.open(out, "w:gz") as tar:
            for child in sorted(ctx.stage.iterdir()):
                tar.add(child, arcname=child.name, filter=root_owned)
        return [out]
