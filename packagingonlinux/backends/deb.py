from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from packagingonlinux import deps, staging
from packagingonlinux.backends.base import Backend, BuildContext
from packagingonlinux.runner import run

_SECTIONS = {
    "AudioVideo": "video", "Audio": "sound", "Video": "video", "Development": "devel",
    "Education": "education", "Game": "games", "Graphics": "graphics", "Network": "net",
    "Office": "editors", "Science": "science", "Settings": "admin", "System": "admin",
    "Utility": "utils",
}


def control_description(summary: str, description: str) -> str:
    lines = [summary]
    for paragraph in description.strip().split("\n\n"):
        text = " ".join(paragraph.split())
        if not text or text == summary:
            continue
        if len(lines) > 1:
            lines.append(" .")
        lines.append(" " + text)
    return "\n".join(lines)


class DebBackend(Backend):
    name = "deb"
    label = "Debian / Ubuntu (.deb)"
    required_tools = ("dpkg-deb",)
    install_hint = "apt install dpkg  (or build in a debian container)"

    def build(self, ctx: BuildContext) -> list[Path]:
        spec = ctx.spec
        deb_arch = spec.arch[0]
        root = ctx.workdir / "root"
        shutil.copytree(ctx.stage, root, symlinks=True)

        depends = list(spec.deps_deb)
        if spec.deps_auto:
            app_files = [spec.binary] if spec.binary else [spec.dir]
            detected = deps.detect_deb([p for p in app_files if p])
            names = {d.split()[0] for d in depends}
            depends += [d for d in detected if d.split()[0] not in names]
            if detected:
                ctx.log(f"detected dependencies: {', '.join(detected)}")
            elif deps.elf_files([p for p in app_files if p]):
                ctx.log("warning: no dependency detected. The app's shared libraries must be installed "
                        "on the build machine for detection to work; otherwise list them in [deps] deb.")

        control = {
            "Package": spec.package_name,
            "Version": spec.version,
            "Architecture": deb_arch,
            "Maintainer": spec.maintainer or "Unknown <unknown@localhost>",
            "Installed-Size": str(staging.installed_size_kib(ctx.stage)),
            "Depends": ", ".join(depends),
            "Section": _SECTIONS.get(spec.categories[0], "misc"),
            "Priority": "optional",
            "Homepage": spec.homepage,
            "Description": control_description(spec.summary, spec.description_text),
        }
        debian = root / "DEBIAN"
        debian.mkdir()
        debian.chmod(0o755)  # dpkg-deb rejects anything else, and mkdir's mode is masked by the umask
        (debian / "control").write_text(
            "".join(f"{k}: {v}\n" for k, v in control.items() if v), encoding="utf-8"
        )
        md5 = []
        for p in sorted(root.rglob("*")):
            if p.is_file() and not p.is_symlink() and debian not in p.parents:
                digest = hashlib.md5(p.read_bytes()).hexdigest()
                md5.append(f"{digest}  {p.relative_to(root).as_posix()}\n")
        (debian / "md5sums").write_text("".join(md5))
        for f in debian.iterdir():
            f.chmod(0o644)
        # Desktop database and icon caches are refreshed by dpkg triggers: no postinst needed.

        out = ctx.outdir / f"{spec.package_name}_{spec.version}_{deb_arch}.deb"
        run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(root), str(out)], ctx.log)
        return [out]
