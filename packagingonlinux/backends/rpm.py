from __future__ import annotations

from pathlib import Path

from packagingonlinux import staging
from packagingonlinux.backends.base import Backend, BuildContext
from packagingonlinux.runner import run


def _quote(path: str) -> str:
    return f'"{path}"' if any(c.isspace() for c in path) else path


def spec_file(ctx: BuildContext) -> str:
    spec = ctx.spec
    rpm_arch = spec.arch[1]
    files = [_quote(f) for f in staging.installed_files(ctx.stage)]
    if spec.dir:
        libdir = ctx.stage / "usr/lib" / spec.package_name
        owned = [libdir] + [d for d in sorted(libdir.rglob("*")) if d.is_dir() and not d.is_symlink()]
        files = [f"%dir {_quote('/' + d.relative_to(ctx.stage).as_posix())}" for d in owned] + files
    requires = "".join(f"Requires: {r}\n" for r in spec.deps_rpm)
    url = f"URL: {spec.homepage}\n" if spec.homepage else ""
    packager = f"Packager: {spec.maintainer}\n" if spec.maintainer else ""
    autoreq = "" if spec.deps_auto else "AutoReq: no\n"
    description = spec.description_text.replace("%", "%%")
    return f"""# Prebuilt binaries: no debuginfo extraction, no stripping, no rpath checks.
%global debug_package %{{nil}}
%global __strip /bin/true
%global __brp_check_rpaths %{{nil}}
%global _build_id_links none

Name: {spec.package_name}
Version: {spec.version}
Release: 1%{{?dist}}
Summary: {spec.summary.replace('%', '%%')}
License: {spec.license}
{url}{packager}BuildArch: {rpm_arch}
{autoreq}{requires}
%description
{description}

%install
mkdir -p %{{buildroot}}
cp -a {ctx.stage}/. %{{buildroot}}/

%files
{chr(10).join(files)}
"""


class RpmBackend(Backend):
    name = "rpm"
    label = "Fedora / openSUSE / RHEL (.rpm)"
    required_tools = ("rpmbuild",)
    install_hint = "dnf install rpm-build  |  apt install rpm  (or build in a fedora container)"

    def build(self, ctx: BuildContext) -> list[Path]:
        spec = ctx.spec
        topdir = ctx.workdir / "rpmbuild"
        (topdir / "SPECS").mkdir(parents=True)
        spec_path = topdir / "SPECS" / f"{spec.package_name}.spec"
        spec_path.write_text(spec_file(ctx), encoding="utf-8")
        cmd = ["rpmbuild", "-bb", "--define", f"_topdir {topdir}"]
        if spec.arch[1] != "noarch":
            cmd += ["--target", spec.arch[1]]
        run(cmd + [str(spec_path)], ctx.log)
        results = []
        for rpm in (topdir / "RPMS").rglob("*.rpm"):
            dest = ctx.outdir / rpm.name
            rpm.replace(dest)
            results.append(dest)
        return results
