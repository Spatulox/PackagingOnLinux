# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

PackagingOnLinux is a single-interface tool that packages any prebuilt software into Linux distribution formats (AppImage, Flatpak, Snap, deb, rpm, etc.). The user describes the app once, picks the formats, and gets all the packages. It must work on any distro and any desktop environment, and run unattended in GitHub/GitLab CI. Inspired by casey-SK/helloWorld-deb-rpm-flatpak-appImage.

The full roadmap and progress are in `PLAN.md` (French). Done so far: Python core, CLI, Qt GUI, deb/rpm/tar.gz backends. Still to do: CI templates (`ci/`), AppImage, Flatpak and Snap backends, `--container` builds, an EN/FR interface language setting, and Windows `.exe` packaging.

The GUI is in French; CLI output and code are in English. `ressources/steps.md` (French) is the original deb feature checklist, modeled on Debreate.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[gui,test]'
QT_QPA_PLATFORM=offscreen .venv/bin/pytest                       # all tests (GUI tests need the env var headless)
.venv/bin/pytest tests/test_build.py::test_build_deb_and_tarball  # a single test

python3 -m packagingonlinux doctor                       # which formats this machine can build
python3 -m packagingonlinux check -c path/packaging.toml # validate config + desktop-file-validate + appstreamcli
python3 -m packagingonlinux build -c path/packaging.toml [-f deb,rpm] [-o outdir]
.venv/bin/packagingonlinux-gui [packaging.toml]          # or: python3 -m packagingonlinux gui
```

The core needs only Python ≥ 3.11 with no dependencies (`tomllib`). The GUI runs on PySide6 (the pip `[gui]` extra) or PyQt6 (what distros package, and what the self-built deb/rpm depend on). GUI modules import Qt names only from `packagingonlinux/gui/qt.py`, never from PySide6/PyQt6 directly, and must use fully scoped enums (`Qt.AlignmentFlag.AlignCenter`), which PyQt6 requires. Don't import Qt outside `packagingonlinux/gui/`. rpm builds can be tested from a non-rpm host with `docker run --rm -v "$PWD":/src:ro fedora:latest` (install `rpm-build python3`). Docker Desktop cannot mount `/tmp`, so keep outputs inside the container.

## Commits

Make one commit per feature or bug fix. Don't bundle unrelated changes into one commit, and don't let a single feature sprawl across several partial commits.

## Architecture

- `packaging.toml` is the exchange format between the GUI, the CLI and CI. `config.py` maps it to the `AppSpec` dataclass. Paths are resolved against the config file's directory on load and written back relative to it on save. `examples/mygesclient/packaging.toml` is the reference config.
- `core.build()` is the only entry point for building, used by both the CLI and the GUI (via the `QThread` in `gui/worker.py`). It runs the optional `[build] command`, validates, builds **one** FHS staging tree (`staging.py`), then runs each backend on it. A failing or unavailable backend is recorded in `BuildResult.errors` and does not stop the others.
- Backends (`backends/`) subclass `Backend`: `required_tools` drives `doctor` and the GUI checkboxes, and `build(ctx)` copies `ctx.stage` (never modify it in place) and writes to `ctx.outdir`. To register a new one, add it to `BACKENDS` in `backends/__init__.py`; it then appears automatically in the CLI and GUI.
- The staging tree uses only freedesktop standards: `<id>.desktop`, a hicolor icon (non-square or non-standard PNG sizes fall back to `/usr/share/pixmaps` with a warning), and AppStream metainfo. App ids are reverse-DNS (required for Flatpak).
- No root needed to build: deb uses `dpkg-deb --root-owner-group`, rpm uses a temporary `_topdir`. There are no maintainer scripts; dpkg/rpm triggers refresh the desktop and icon caches.
- Architecture is read from the ELF header (`elf.py`); scripts are `all`/`noarch`. Dependencies: deb uses `dpkg-shlibdeps`, falling back to ldd + `dpkg -S` (`deps.py`), which only works if the libraries are installed on the build machine. rpm relies on rpmbuild's AutoReq.

## Known issue with the MyGesClient binary

It links WebKitGTK 4.0, which current Fedora no longer ships, so its rpm builds correctly but won't install there. Rebuilding with Wails `-tags webkit2_41` fixes it. This is not a packaging bug.
