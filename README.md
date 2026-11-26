# PackagingOnLinux

Package any prebuilt application into several Linux distribution formats, and into a Windows installer and zip, from a single description and without leaving Linux. You describe the app once (name, binary, icon, metadata) in a `packaging.toml`, pick the formats, and get all the packages. It works from a graphical interface, from the command line, and unattended in CI.

| Format | Status |
|---|---|
| deb | done |
| rpm | done |
| tar.gz | done |
| AppImage | done |
| Flatpak | done |
| Snap | done |
| Windows installer (`setup.exe`, NSIS) | done |
| Windows portable `.zip` | done |

The input is software that is **already compiled** (a binary or an install folder), one per platform. An optional build command per platform can compile it right before packaging. The roadmap is in [`docs/PLAN.md`](docs/PLAN.md) (French).

Inspired by [casey-SK/helloWorld-deb-rpm-flatpak-appImage](https://github.com/casey-SK/helloWorld-deb-rpm-flatpak-appImage).

## Install

The core only needs Python ≥ 3.11. The graphical interface also needs Qt for Python (PyQt6 or PySide6).

From a release package:

```bash
sudo apt install ./packagingonlinux_*_all.deb   # Debian / Ubuntu (pulls in python3-pyqt6)
sudo dnf install ./packagingonlinux-*.rpm        # Fedora
```

Use `apt install ./file.deb` rather than `dpkg -i`, which does not install dependencies.

The AppImage, Flatpak and Snap include their own Python and Qt, so they work on any distribution:

```bash
chmod +x PackagingOnLinux-*.AppImage && ./PackagingOnLinux-*.AppImage   # nothing to install
flatpak install --user --bundle PackagingOnLinux-*.flatpak               # pulls the runtime from Flathub
sudo snap install --dangerous --classic packagingonlinux_*.snap
```

To build packages, PackagingOnLinux runs tools installed on your system (`dpkg-deb`, `rpmbuild`, your build command...). Its Flatpak therefore runs them outside its sandbox (with `flatpak-spawn --host`) and can read and write your home folder, and its snap uses classic confinement. Both have the same access as the deb.

From the sources:

```bash
python3 -m packagingonlinux --help      # no installation, CLI only
pipx install '.[gui]'                    # or install it, with the GUI
```

## Usage

### Graphical interface

```bash
packagingonlinux-gui [packaging.toml]   # or: packagingonlinux gui
```

Fill in the form, choose the binary and the icon (in the Linux tab, and in the Windows tab for Windows formats), tick the formats, then click « Construire les paquets ». Formats whose tools are missing on the machine are greyed out; hover them to see the command that installs the missing tools. The interface is in French.

Started from the desktop menu rather than a terminal, the GUI first loads the environment of your login shell (`$SHELL -ilc`, so `~/.profile`, `~/.bashrc`, `~/.zshrc`...), like code editors do: build commands then find the tools that only your shell startup files put in `PATH` (e.g. `~/go/bin/wails`, or `npm` from nvm). If that fails, the build log says so. Set `PACKAGINGONLINUX_NO_SHELL_ENV=1` to turn it off.

### Command line

```bash
packagingonlinux init                                  # create a packaging.toml interactively
packagingonlinux doctor                                # which formats this machine can build
packagingonlinux check -c packaging.toml               # validate the config and generated metadata
packagingonlinux build -c packaging.toml [-f deb,rpm] [-o dist] [--version 1.2.0~beta]
```

`--version` replaces `[app] version` without editing the file (the build command gets it in `$APP_VERSION`), e.g. to use the version of a release tag.

A failing format does not stop the others; errors are listed at the end. `packagingonlinux --help` lists the formats, the tools each one needs, examples and exit statuses; the full reference is the man page, readable from the sources with `man -l docs/man/packagingonlinux.1`.

The `appimage` format needs `mksquashfs` (`squashfs-tools`). The first build downloads the AppImage runtime (a pinned release, checked against its sha256) into `~/.cache/packagingonlinux/`; offline, download it yourself and set `PACKAGINGONLINUX_APPIMAGE_RUNTIME` to its path. The app's libraries are not bundled: like the tar.gz, the AppImage uses those of the user's system.

The `flatpak` format needs `flatpak` and `flatpak-builder` (plus `librsvg2-common` for an SVG icon), and a square icon. The first build installs the runtime and its SDK for the current user from Flathub. The app runs on that runtime, in a sandbox: `[flatpak] finish_args` lists what it may access (by default the display and the GPU, not the user's files; add `--filesystem=home`, `--share=network`… as needed). Install the result with `flatpak install --user --bundle <file>.flatpak`.

The `snap` format needs `snapcraft` (`snap install snapcraft --classic`). By default it builds in an LXD container (`lxd init --auto` once); in CI, on the Ubuntu release matching `[snap] base` (24.04 for `core24`), set `SNAPCRAFT_BUILD_ENVIRONMENT=host` and run the build as root. This is the only format that may need root. The snap name is the package name (lowercase app name): at most 40 characters among `a-z`, `0-9` and `-`. Install the result with `snap install --dangerous <file>.snap` (add `--classic` for a classic snap).

## `packaging.toml`

The GUI, the CLI and CI all read the same file, so you can set a project up in the GUI, commit the file, and let CI produce the same packages. Paths are relative to the file.

```toml
[app]
id = "io.github.you.MyApp"        # reverse-DNS, required by Flatpak
name = "MyApp"
version = "1.0.0"
summary = "One-line description"
license = "GPL-3.0-only"
maintainer = "You"
categories = ["Utility"]

[linux]
command = "make"                  # optional, see below
binary = "build/myapp"            # or: dir = "dist/" + exec = "bin/myapp"
icon = "icons/myapp.png"          # square PNG or SVG
man = ["docs/myapp.1"]            # optional man pages (name ends with the section)

[windows]                         # optional: only for the zip and nsis formats
command = "make windows"
binary = "build/myapp.exe"        # or: dir = "dist-win/" + exec = "myapp.exe"
icon = "icons/myapp.ico"          # optional: .ico or square PNG ≤ 256 px, else the Linux icon

[deps]                            # Linux only
auto = true                       # detect shared library dependencies
deb = ["libgtk-3-0"]              # extra dependencies, per format
rpm = ["gtk3"]

[flatpak]                         # optional, these are the defaults
runtime = "org.freedesktop.Platform"
runtime_version = "26.08"
sdk = ""                          # empty: the runtime's SDK (org.freedesktop.Sdk)
finish_args = ["--share=ipc", "--socket=wayland", "--socket=fallback-x11", "--device=dri"]

[snap]                            # optional, these are the defaults
base = "core24"
confinement = "strict"            # or "classic" (same access as a deb), "devmode"
grade = ""                        # empty: "devel" if the version has a "~", else "stable"
plugs = ["desktop", "desktop-legacy", "wayland", "x11", "opengl", "home", "network"]
extensions = []                   # e.g. ["gnome"] for a GTK app, ["kde-neon-6"] for Qt 6
stage_packages = []               # Ubuntu packages to bundle (libraries the base lacks)

[output]
formats = ["deb", "rpm", "tarball", "zip", "nsis"]
dir = "dist"
```

A platform's `command` runs in the config's folder before packaging, only when a format of that platform is built (so `-f deb` never runs the Windows build). It receives `$APP_ID`, `$APP_NAME`, `$APP_VERSION` and `$APP_PLATFORM` (`linux` or `windows`). Older configs with `[files]` and `[build] command` are still read as `[linux]`.

Example: [`packaging.toml`](packaging.toml), which packages PackagingOnLinux itself.

Every section and key, with its type and default, is described in the `packaging.toml(5)` man page ([`docs/man/packaging.toml.5`](docs/man/packaging.toml.5), `man -l docs/man/packaging.toml.5`).

Packages only use freedesktop standards (a `.desktop` file, a hicolor icon and AppStream metainfo), so the app appears in the menus of any desktop environment. Building never needs root.

## Windows

A Linux binary does not run on Windows, so Windows formats need a Windows executable (`.exe`) in `[windows]`. Most toolchains can produce one from Linux, which is what `[windows] command` is for:

| Toolchain | Command |
|---|---|
| Wails | `wails build -platform windows/amd64` |
| Go | `GOOS=windows GOARCH=amd64 go build -o build/myapp.exe` |
| Rust | `cargo build --release --target x86_64-pc-windows-gnu` (needs mingw-w64) |

The architecture (x86, x64, arm64) is read from the executable. Two formats are built from it:

- `zip`: a portable `<Name>-<version>-windows-<arch>.zip`. Unzip it anywhere and run the `.exe`. No tool needed.
- `nsis`: an installer, `<Name>-<version>-windows-<arch>-setup.exe`, made with `makensis` (`apt install nsis`, `dnf install mingw32-nsis`). It installs for the current user into `%LOCALAPPDATA%\Programs\<Name>` without administrator rights, adds a Start menu shortcut (and a desktop one if ticked), and registers the app with its uninstaller in Windows' "Apps" settings. `setup.exe /S` installs silently.

The installer is not signed, so on first launch Windows SmartScreen warns that the publisher is unknown ("More info" → "Run anyway"). Code signing needs a certificate and is not supported yet.

## CI (GitHub Actions)

Other repositories build their packages with the reusable workflow `.github/workflows/package.yml`. It runs only what `packaging.toml` describes: the `[linux]` / `[windows]` command (which may call a script of the project), then every format, with the needed packaging tools installed. The packages are uploaded as artifacts named `release-packages` (and `release-packages-snap`), ready for [release-kit](https://github.com/Spatulox/release-kit) to attach to a GitHub release:

```yaml
# .github/workflows/build.yml, called by release-kit's release.yml with the decoded tag
on:
  workflow_call:
    inputs:
      debversion:
        type: string
        required: true

jobs:
  packages:
    uses: Spatulox/PackagingOnLinux/.github/workflows/package.yml@v0
    with:
      version: ${{ inputs.debversion }}   # 1.2.0~beta for the tag v1.2.0_beta
      dockerfile: .github/build.Dockerfile
```

Whatever the language, the build command's toolchain comes from a **build image** the project describes: a `dockerfile` (built by the workflow, cached between runs) or a public `image`. The workflow adds Python and the packaging tools on top of it (with `apt-get` or `dnf`, so the image must be based on Debian, Ubuntu, Fedora or RHEL), then runs the whole build in it. The packages' dependencies are those of that image's distribution. For example, a Wails app:

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
      golang-go nodejs npm build-essential pkg-config libgtk-3-dev libwebkit2gtk-4.1-dev
RUN GOBIN=/usr/local/bin go install github.com/wailsapp/wails/v2/cmd/wails@v2.10.1
```

Without `dockerfile` or `image`, the build runs on the Ubuntu runner itself (enough for an app that needs nothing more, or that is already built by an earlier job and downloaded).

| Input | Default | |
|---|---|---|
| `config` | `packaging.toml` | Path of the config |
| `formats` | `[output] formats` | Comma-separated formats to build |
| `version` | `[app] version` | Version of the packages |
| `artifact-name` | `release-packages` | Name of the uploaded artifact (the snap goes in `<name>-snap`) |
| `dockerfile` | none | Dockerfile of the build environment, in the repository (context: the repository root) |
| `build-args` | none | Build arguments of the `dockerfile`, one `NAME=value` per line (e.g. `BASE=ubuntu:26.04`) |
| `image` | none | Public image of the build environment instead (e.g. `ubuntu:26.04`, `fedora:latest`) |
| `download`, `download-path` | none, `.` | Artifacts of earlier jobs to download first, e.g. a Windows `.exe` built on a Windows runner. A `.tar` at their top is extracted (artifacts lose the executable bit) |
| `runs-on` | `ubuntu-24.04` | Runner of the main job (e.g. `ubuntu-22.04` for an older glibc) |
| `packagingonlinux-ref` | `v0` | PackagingOnLinux version |

Every format but snap is built in one job, so the build command runs once; the snap is built in a second job, as root, on the Ubuntu release of `[snap] base`, and can't be built with a build image (snapcraft doesn't run in Docker). A matrix of calls builds one package per distribution release or per architecture (`image: ubuntu:${{ matrix.ubuntu }}`, `runs-on: ubuntu-24.04-arm`, a distinct `artifact-name` each). `v0` follows the latest stable 0.x release. [`ci/github/example-build.yml`](ci/github/example-build.yml) is a complete example, and this repository's own `.github/workflows/build.yml` uses it to release PackagingOnLinux.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[gui,test]'
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

rpm packages can be built from a non-rpm distro in a container: `docker run --rm -v "$PWD":/src:ro fedora:latest` (install `rpm-build python3`).

## License

[GPL-3.0](LICENSE.md)
