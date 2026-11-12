# PackagingOnLinux

Package any prebuilt application into several Linux distribution formats, and into a Windows installer and zip, from a single description and without leaving Linux. You describe the app once (name, binary, icon, metadata) in a `packaging.toml`, pick the formats, and get all the packages. It works from a graphical interface, from the command line, and unattended in CI.

| Format | Status |
|---|---|
| deb | done |
| rpm | done |
| tar.gz | done |
| AppImage, Flatpak, Snap | planned |
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

### Command line

```bash
packagingonlinux init                                  # create a packaging.toml interactively
packagingonlinux doctor                                # which formats this machine can build
packagingonlinux check -c packaging.toml               # validate the config and generated metadata
packagingonlinux build -c packaging.toml [-f deb,rpm] [-o builds]
```

A failing format does not stop the others; errors are listed at the end.

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

[windows]                         # optional: only for the zip and nsis formats
command = "make windows"
binary = "build/myapp.exe"        # or: dir = "dist-win/" + exec = "myapp.exe"
icon = "icons/myapp.ico"          # optional: .ico or square PNG ≤ 256 px, else the Linux icon

[deps]                            # Linux only
auto = true                       # detect shared library dependencies
deb = ["libgtk-3-0"]              # extra dependencies, per format
rpm = ["gtk3"]

[output]
formats = ["deb", "rpm", "tarball", "zip", "nsis"]
dir = "builds"
```

A platform's `command` runs in the config's folder before packaging, only when a format of that platform is built (so `-f deb` never runs the Windows build). It receives `$APP_ID`, `$APP_NAME`, `$APP_VERSION` and `$APP_PLATFORM` (`linux` or `windows`). Older configs with `[files]` and `[build] command` are still read as `[linux]`.

Example: [`packaging.toml`](packaging.toml), which packages PackagingOnLinux itself.

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

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[gui,test]'
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

rpm packages can be built from a non-rpm distro in a container: `docker run --rm -v "$PWD":/src:ro fedora:latest` (install `rpm-build python3`).

## License

[GPL-3.0](LICENSE.md)
