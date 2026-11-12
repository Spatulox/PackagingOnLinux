from __future__ import annotations

import zipfile
from pathlib import Path

from packagingonlinux.windows import staging
from packagingonlinux.backend import Backend, BuildContext


class ZipBackend(Backend):
    """Portable Windows app: unzip anywhere and run the .exe, nothing is installed."""

    name = "zip"
    label = "Windows portable (.zip)"
    platform = "windows"

    def build(self, ctx: BuildContext) -> list[Path]:
        spec = ctx.spec
        out = ctx.outdir / f"{spec.file_stem}-{spec.version}-windows-{spec.windows_arch}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            for rel in staging.installed_files(ctx.stage):
                zf.write(ctx.stage / rel, f"{spec.file_stem}/{rel}")
        return [out]
