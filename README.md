# PackagingOnLinux

Package any prebuilt Linux application into several distribution formats from a single description. You describe the app once (name, binary, icon, metadata) in a `packaging.toml`, pick the formats, and get all the packages. It works from a graphical interface, from the command line, and unattended in CI.

| Format | Status |
|---|---|
| deb | done |
| rpm | done |
| tar.gz | done |
| AppImage, Flatpak, Snap | planned |
| Windows `.exe` / `.zip` | planned |

The input is software that is **already compiled** (a binary or an install folder). An optional build command in the config can compile it right before packaging. The roadmap is in [`PLAN.md`](PLAN.md) (French).

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

Fill in the form, choose the binary and the icon, tick the formats, then click « Construire les paquets ». Formats whose tools are missing on the machine are greyed out; hover them to see the command that installs the missing tools. The interface is in French.

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

[files]
binary = "build/myapp"            # or: dir = "dist/" + exec = "bin/myapp"
icon = "icons/myapp.png"          # square PNG or SVG

[build]                           # optional; receives $APP_ID, $APP_NAME, $APP_VERSION
command = "make"

[deps]
auto = true                       # detect shared library dependencies
deb = ["libgtk-3-0"]              # extra dependencies, per format
rpm = ["gtk3"]

[output]
formats = ["deb", "rpm", "tarball"]
dir = "builds"
```

Examples: [`examples/mygesclient/packaging.toml`](examples/mygesclient/packaging.toml), and [`packaging.toml`](packaging.toml), which packages PackagingOnLinux itself.

Packages only use freedesktop standards (a `.desktop` file, a hicolor icon and AppStream metainfo), so the app appears in the menus of any desktop environment. Building never needs root.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[gui,test]'
QT_QPA_PLATFORM=offscreen .venv/bin/pytest
```

rpm packages can be built from a non-rpm distro in a container: `docker run --rm -v "$PWD":/src:ro fedora:latest` (install `rpm-build python3`).

## License

[GPL-3.0](LICENSE.md)
