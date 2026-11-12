"""Runtime dependency detection for prebuilt binaries.

deb: dpkg-shlibdeps (versioned, the Debian way), falling back to ldd + `dpkg -S`
     (the approach of the former scripts/list_dep.py).
rpm: nothing to do here, rpmbuild's AutoReq adds `libfoo.so.N()(64bit)` requirements itself.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from packagingonlinux.linux import elf

# Packages present on every Debian-based system: never worth listing.
_DEB_ESSENTIAL = {
    "libc6", "libgcc-s1", "libstdc++6", "zlib1g", "libselinux1", "liblzma5", "libbz2-1.0",
}


def elf_files(paths: list[Path]) -> list[Path]:
    out = []
    for p in paths:
        if p.is_dir():
            out += [f for f in p.rglob("*") if f.is_file() and not f.is_symlink() and elf.is_elf(f)]
        elif elf.is_elf(p):
            out.append(p)
    return out


def _shlibdeps(binaries: list[Path], search_dirs: list[Path]) -> list[str] | None:
    if not shutil.which("dpkg-shlibdeps"):
        return None
    with tempfile.TemporaryDirectory(prefix="col-shlibdeps-") as tmp:
        (Path(tmp) / "debian").mkdir()
        (Path(tmp) / "debian/control").write_text(
            "Source: col-probe\n\nPackage: col-probe\nArchitecture: any\n"
        )
        cmd = ["dpkg-shlibdeps", "-O", "--ignore-missing-info", "--warnings=0"]
        cmd += [f"-l{d}" for d in search_dirs]
        cmd += [f"-e{b}" for b in binaries]
        proc = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    m = re.search(r"^shlibs:Depends=(.*)$", proc.stdout, re.M)
    if not m:
        return []
    return [d.strip() for d in m.group(1).split(",") if d.strip()]


def _ldd_dpkg(binaries: list[Path]) -> list[str]:
    if not (shutil.which("ldd") and shutil.which("dpkg")):
        return []
    libs: set[str] = set()
    for b in binaries:
        proc = subprocess.run(["ldd", str(b)], capture_output=True, text=True)
        libs.update(re.findall(r"=> (/\S+) \(", proc.stdout))
    packages: set[str] = set()
    for lib in sorted(libs):
        proc = subprocess.run(["dpkg", "-S", lib], capture_output=True, text=True)
        if proc.returncode == 0:
            pkg = proc.stdout.split(":")[0].strip()
            if pkg not in _DEB_ESSENTIAL:
                packages.add(pkg)
    return sorted(packages)


def detect_deb(paths: list[Path]) -> list[str]:
    binaries = elf_files(paths)
    if not binaries:
        return []
    search_dirs = sorted({b.parent for b in binaries})
    result = _shlibdeps(binaries, search_dirs)
    if result is None:
        result = _ldd_dpkg(binaries)
    return result
