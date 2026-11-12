# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

PackagingOnLinux is a single-interface tool that packages any prebuilt software into Linux distribution formats (AppImage, Flatpak, Snap, deb, rpm, etc.), and into a Windows installer and zip, all from Linux. The user describes the app once, picks the formats, and gets all the packages. It must work on any distro and any desktop environment, and run unattended in GitHub/GitLab CI. Inspired by casey-SK/helloWorld-deb-rpm-flatpak-appImage.

The full roadmap and progress are in `docs/PLAN.md` (French). Done so far: Python core, CLI, Qt GUI, deb/rpm/tar.gz/AppImage/Flatpak backends, Windows zip and NSIS installer. Still to do: CI templates (`ci/`), the Snap backend, `--container` builds, and an EN/FR interface language setting.

The GUI is in French; CLI output and code are in English. `docs/deb-checklist.md` (French) is the original deb feature checklist, modeled on Debreate.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[gui,test]'
QT_QPA_PLATFORM=offscreen .venv/bin/pytest                       # all tests (GUI tests need the env var headless)
.venv/bin/pytest tests/test_build.py::test_build_deb_and_tarball  # a single test

python3 -m packagingonlinux doctor                       # which formats this machine can build
python3 -m packagingonlinux check -c path/packaging.toml # validate config + desktop-file-validate + appstreamcli
python3 -m packagingonlinux build -c path/packaging.toml [-f deb,rpm] [-o outdir]
.venv/bin/packagingonlinux-gui [packaging.toml]          # or: python3 -m packagingonlinux gui
python3 tools/gen_man.py                                 # regenerate docs/man/packagingonlinux.1 from the CLI parser
```

`docs/man/packagingonlinux.1` is generated from `cli.build_parser()` and its tables (`EXAMPLES`, `EXIT_STATUS`, `ENVIRONMENT`, `FILES`) plus every backend's `label`, `required_tools` and `install_hint`; `tests/test_man.py` fails when it is out of date, so rerun `tools/gen_man.py` after changing any of them or adding a backend. `docs/man/packaging.toml.5` (the config reference) is written by hand: document every new section or key there; `tests/test_man.py` checks that the `Target` keys and every `OPTION_SECTIONS` section and key appear in it.

The core needs only Python ≥ 3.11 with no dependencies (`tomllib`). The GUI runs on PySide6 (the pip `[gui]` extra) or PyQt6 (what distros package, and what the self-built deb/rpm depend on). GUI modules import Qt names only from `packagingonlinux/gui/qt.py`, never from PySide6/PyQt6 directly, and must use fully scoped enums (`Qt.AlignmentFlag.AlignCenter`), which PyQt6 requires. Don't import Qt outside `packagingonlinux/gui/`. rpm builds can be tested from a non-rpm host with `docker run --rm -v "$PWD":/src:ro fedora:latest` (install `rpm-build python3`). Docker Desktop cannot mount `/tmp`, so keep outputs inside the container.

## Commits

Make one commit per feature or bug fix. Don't bundle unrelated changes into one commit, and don't let a single feature sprawl across several partial commits.

## Architecture

- `packaging.toml` is the exchange format between the GUI, the CLI and CI. `config.py` maps it to the `AppSpec` dataclass. Paths are resolved against the config file's directory on load and written back relative to it on save. The root `packaging.toml` (PackagingOnLinux packaging itself) is the reference config; the files it needs (launchers, icons, the `.ico` generator) are in `selfpack/`, which is never imported by the tool.
- What to package is described per platform: `[linux]` and `[windows]` sections, each a `Target` (`command`, `binary` or `dir` + `exec`, `icon`), in `AppSpec.linux` / `AppSpec.windows` (`None` when absent). The old `[files]` + `[build]` layout is still read as `[linux]`.
- `core.build()` is the only entry point for building, used by both the CLI and the GUI (via the `QThread` in `gui/worker.py`). For each platform that has a requested format, it runs that platform's `command`, validates its target, builds **one** staging tree for it (`linux/staging.py` or `windows/staging.py`, via `core.STAGERS`), then runs that platform's backends on it. A failing or unavailable backend, or a failing platform command, is recorded in `BuildResult.errors` and does not stop the others.
- The code is grouped by platform: what is common (`config`, `core`, `cli`, `backend`, `runner`, `png`) sits at the top of `packagingonlinux/`, everything specific to one platform in `linux/` or `windows/` (binary header reader, staging, backends). `linux/__init__.py` and `windows/__init__.py` must stay import-free: `config` imports `linux.elf` and `windows.pe`, so importing backends there would create an import cycle.
- Backends (`linux/*.py`, `windows/*.py`) subclass `backend.Backend`: `platform` (`linux` or `windows`) picks the target and staging tree, `required_tools` drives `doctor` and the GUI checkboxes, and `build(ctx)` copies `ctx.stage` (never modify it in place) and writes to `ctx.outdir`. To register a new one, add it to `BACKENDS` in `core.py`; it then appears automatically in the CLI and GUI.
- The staging tree uses only freedesktop standards: `<id>.desktop`, a hicolor icon (non-square or non-standard PNG sizes fall back to `/usr/share/pixmaps` with a warning), and AppStream metainfo. App ids are reverse-DNS (required for Flatpak).
- No root needed to build: deb uses `dpkg-deb --root-owner-group`, rpm uses a temporary `_topdir`. There are no maintainer scripts; dpkg/rpm triggers refresh the desktop and icon caches.
- Windows: `windows/pe.py` reads the architecture from the PE header (x86/x64/arm64), `windows/ico.py` makes the `.ico` in pure Python (an .ico as is, or a square PNG ≤ 256 px wrapped in an ICO header). The `nsis` backend generates a per-user installer script (`%LOCALAPPDATA%\Programs`, HKCU only, no admin) compiled by `makensis`. makensis takes `File` source paths literally (`$` can't be escaped), so payload files get plain names and the real name goes in `/oname`.
- AppImage (`linux/appimage.py`) is the type2 runtime followed by a `mksquashfs` image of an AppDir (stage + `AppRun` + root `.desktop` and icon); no appimagetool or FUSE. The runtime is a pinned release checked by sha256, cached in `~/.cache/packagingonlinux/` (`$PACKAGINGONLINUX_APPIMAGE_RUNTIME` overrides it, which tests use). Don't run built AppImages in tests: desktop integration daemons (AppImageLauncher) may grab them.
- Per-format options live in their own optional section (`[flatpak]` -> `AppSpec.flatpak`, a `FlatpakOptions`). `to_toml` writes only the values that differ from the defaults (`OPTION_SECTIONS`). The GUI has no widgets for them, so `AppForm` keeps the loaded ones and puts them back in `to_spec`: a new option section must be handled there too, or saving from the GUI drops it.
- Flatpak (`linux/flatpak.py`): a generated manifest with one `simple` module copying the stage's `usr/` to `/app`, built by `flatpak-builder --user --install-deps-from=flathub` into a repo in the work dir, then `flatpak build-bundle`. Needs a hicolor icon (no pixmaps fallback). Tested for real only in a privileged container (`docker run --privileged --network host ubuntu:24.04`, `apt install flatpak flatpak-builder librsvg2-common`; `flatpak run` there also needs `dbus-daemon --system --fork` and `dbus-run-session`).
- Linux architecture is read from the ELF header (`linux/elf.py`); scripts are `all`/`noarch`. Dependencies: deb uses `dpkg-shlibdeps`, falling back to ldd + `dpkg -S` (`linux/deps.py`), which only works if the libraries are installed on the build machine. rpm relies on rpmbuild's AutoReq.
