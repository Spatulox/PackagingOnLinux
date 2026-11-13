"""Runtime dependency detection for prebuilt binaries.

deb: dpkg-shlibdeps (versioned, the Debian way), falling back to ldd + `dpkg -S`
     (the approach of the former scripts/list_dep.py).
rpm: nothing to do here, rpmbuild's AutoReq adds `libfoo.so.N()(64bit)` requirements itself.
"""

from __future__ import annotations

import re
from pathlib import Path

from packagingonlinux.linux import elf
from packagingonlinux.runner import capture, temp_dir, which

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
    if not which("dpkg-shlibdeps"):
        return None
    with temp_dir(prefix="col-shlibdeps-") as tmp:
        (Path(tmp) / "debian").mkdir()
        (Path(tmp) / "debian/control").write_text(
            "Source: col-probe\n\nPackage: col-probe\nArchitecture: any\n"
        )
        cmd = ["dpkg-shlibdeps", "-O", "--ignore-missing-info", "--warnings=0"]
        cmd += [f"-l{d}" for d in search_dirs]
        cmd += [f"-e{b}" for b in binaries]
        proc = capture(cmd, cwd=Path(tmp))
    if proc.returncode != 0:
        return None
    m = re.search(r"^shlibs:Depends=(.*)$", proc.stdout, re.M)
    if not m:
        return []
    return [d.strip() for d in m.group(1).split(",") if d.strip()]


def _ldd_dpkg(binaries: list[Path]) -> list[str]:
    if not (which("ldd") and which("dpkg")):
        return []
    libs: set[str] = set()
    for b in binaries:
        proc = capture(["ldd", str(b)])
        libs.update(re.findall(r"=> (/\S+) \(", proc.stdout))
    packages: set[str] = set()
    for lib in sorted(libs):
        proc = capture(["dpkg", "-S", lib])
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
