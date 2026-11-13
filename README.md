# PackagingOnLinux

Package any prebuilt application into the Linux distribution formats, and into a Windows installer and zip, from a single description. You describe the app once (name, binary, icon, metadata) in a `packaging.toml`, pick the formats, and get all the packages. It works from a graphical interface, from the command line and unattended in CI, on any Linux distribution, and on Windows through Docker.

| Format | `-f` name | Tools needed on a Linux host | With `--container` (and on Windows) |
|---|---|---|---|
| Debian / Ubuntu `.deb` | `deb` | `dpkg-deb` | yes |
| Fedora / openSUSE / RHEL `.rpm` | `rpm` | `rpmbuild` | yes |
| `.tar.gz` | `tarball` | none | yes |
| AppImage | `appimage` | `mksquashfs` | yes |
| Flatpak bundle | `flatpak` | `flatpak`, `flatpak-builder` | yes |
| Snap | `snap` | `snapcraft` | no |
| Windows installer (`setup.exe`, NSIS) | `nsis` | `makensis` | built on the host |
| Windows portable `.zip` | `zip` | none | built on the host |

The input is software that is **already compiled** (a binary or an install folder), one per platform. An optional build command per platform can compile it right before packaging. The roadmap is in [`docs/PLAN.md`](docs/PLAN.md) (French), the changes in [`CHANGELOG.md`](CHANGELOG.md).

Inspired by [casey-SK/helloWorld-deb-rpm-flatpak-appImage](https://github.com/casey-SK/helloWorld-deb-rpm-flatpak-appImage).

## Install

### Linux

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

To build packages, PackagingOnLinux runs tools installed on your system (`dpkg-deb`, `rpmbuild`, your build command...). Its Flatpak therefore runs them outside its sandbox (with `flatpak-spawn --host`) and can read and write your home folder, and its snap uses classic confinement. Both have the same access as the deb. `--container` is not available from the AppImage and the Flatpak, because Docker can't see their files: use another version for it.

### Windows

Install PackagingOnLinux with `PackagingOnLinux-<version>-windows-x64-setup.exe` from a release. It installs for the current user, without administrator rights. You can also unzip the portable `.zip` anywhere. Then:

- for the Linux formats, install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) and start it. On Windows, PackagingOnLinux builds them in a container by default (see [below](#building-in-a-container-and-from-windows));
- for the Windows installer (`nsis`), install [NSIS](https://nsis.sourceforge.io/) and add its folder (`C:\Program Files (x86)\NSIS`) to the `PATH`. The `zip` format needs nothing.

### From the sources

The core only needs Python ≥ 3.11, and the GUI also needs Qt for Python (PyQt6 or PySide6):

```bash
python3 -m packagingonlinux --help      # no installation, CLI only
pipx install '.[gui]'                    # or install it, with the GUI (on Windows: py -m pip install .[gui])
```

## Usage

### Graphical interface

```bash
packagingonlinux-gui [packaging.toml]   # or: packagingonlinux gui
```

1. Fill in the form, and choose the binary and the icon in the Linux tab (and in the Windows tab for the Windows formats).
2. Tick the formats. A format that can't be built here is greyed out: hover it to see why, and the command that installs the missing tools.
3. Tick « Construire dans un conteneur Docker » to build the Linux formats in a container. It is ticked by default on Windows.
4. Click « Construire les paquets ».

The interface is in French.

### Command line

```bash
packagingonlinux init                                  # create a packaging.toml interactively
packagingonlinux doctor                                # which formats this machine can build, and whether Docker works
packagingonlinux check -c packaging.toml               # validate the config and generated metadata
packagingonlinux build -c packaging.toml [-f deb,rpm] [-o dist] [--container | --no-container]
```

A failing format does not stop the others; errors are listed at the end. `doctor` prints one line per format, and a last one for Docker:

```
PackagingOnLinux 0.2.0
  ok       linux    deb       Debian / Ubuntu (.deb)
  missing  linux    rpm       Fedora / openSUSE / RHEL (.rpm): needs rpmbuild
                              install: dnf install rpm-build  |  apt install rpm  (or build with --container)
  ...
  ok       linux    container Docker 29.1.1 (used with --container)
```

`packagingonlinux --help` lists the formats, the tools each one needs, examples, exit statuses and environment variables. The full reference is the man page, readable from the sources with `man -l docs/man/packagingonlinux.1`.

## Building in a container (and from Windows)

With `--container`, the Linux side of the build runs in a Docker container that has every packaging tool. This includes the `[linux] command` and all the Linux formats but snap. It lets you build an `.rpm` on Debian, or every Linux package on a machine that has none of the tools. On Windows it is the default, since the Linux tools don't exist there; `--no-container` turns it off, and the Linux formats are then refused.

- **Requirements**: Docker Desktop (Windows, macOS) or Docker Engine (Linux), installed and running. If Docker is missing or stopped, the build stops before building anything, with a message saying what to do (exit status 2; an error dialog in the GUI).
- **First use**: the image `packagingonlinux-builder` (Ubuntu 24.04 and the packaging tools) is built once, which takes a few minutes. The AppImage runtime and the Flatpak runtimes are kept in the `packagingonlinux-cache` Docker volume, so later builds don't download them again. Remove the volume with `docker volume rm packagingonlinux-cache`.
- **What the container sees**: only the config's folder, mounted as the working directory, and the output folder. Every `[linux]` file (binary or dir, icon, man pages) must be inside the config's folder, and the `[linux] command` runs there under Linux. On a Linux or macOS host, the container runs as your user, so the files it writes belong to you.
- **The Windows side stays on the host**: the `[windows] command` (e.g. PyInstaller or `go build` on Windows) and the `zip` and `nsis` formats run on the machine itself.
- **A custom image**: the image has the packaging tools but no compiler. If your `[linux] command` needs one, build an image `FROM` PackagingOnLinux's (shown by the first build) with your toolchain added, and set `PACKAGINGONLINUX_CONTAINER_IMAGE` to its name.
- **Limits**:
  - snap can't be built in a container, because snapcraft is only distributed as a snap: build it on Linux or in CI;
  - Flatpak builds use a privileged container (`flatpak-builder` sandboxes the build);
  - `[deps] auto` only finds the libraries installed in the image, so list your app's dependencies in `[deps] deb`;
  - on Windows, if git checks out your scripts with CRLF line endings (`core.autocrlf`), they fail under Linux: add a `.gitattributes` with `*.sh text eol=lf` (and the same for your launchers).

## Formats

The `appimage` format needs `mksquashfs` (`squashfs-tools`). The first build downloads the AppImage runtime (a pinned release, checked against its sha256) into `~/.cache/packagingonlinux/`. Offline, download it yourself and set `PACKAGINGONLINUX_APPIMAGE_RUNTIME` to its path. The app's libraries are not bundled: like the tar.gz, the AppImage uses those of the user's system.

The `flatpak` format needs `flatpak` and `flatpak-builder` (plus `librsvg2-common` for an SVG icon), and a square icon. The first build installs the runtime and its SDK for the current user from Flathub. The app runs on that runtime, in a sandbox: `[flatpak] finish_args` lists what it may access. By default that is the display and the GPU, not the user's files; add `--filesystem=home`, `--share=network`… as needed. Install the result with `flatpak install --user --bundle <file>.flatpak`.

The `snap` format needs `snapcraft` (`snap install snapcraft --classic`).
- By default it builds in an LXD container (run `lxd init --auto` once).
- In CI, on the Ubuntu release matching `[snap] base` (24.04 for `core24`), set `SNAPCRAFT_BUILD_ENVIRONMENT=host` and run the build as root. This is the only format that may need root.
- The snap name is the package name (lowercase app name): at most 40 characters among `a-z`, `0-9` and `-`.
- Install the result with `snap install --dangerous <file>.snap` (add `--classic` for a classic snap).

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

A platform's `command` runs in the config's folder before packaging, only when a format of that platform is built: `-f deb` never runs the Windows build.
- It runs with the shell of the machine that runs it: `sh` on Linux and in the container, `cmd.exe` for a `[windows] command` on Windows.
- It receives `$APP_ID`, `$APP_NAME`, `$APP_VERSION` and `$APP_PLATFORM` (`linux` or `windows`).

Older configs with `[files]` and `[build] command` are still read as `[linux]`. `-c -` reads the config from standard input, with paths relative to the current directory.

Example: [`packaging.toml`](packaging.toml), which packages PackagingOnLinux itself.

Every section and key, with its type and default, is described in the `packaging.toml(5)` man page ([`docs/man/packaging.toml.5`](docs/man/packaging.toml.5), `man -l docs/man/packaging.toml.5`).

Linux packages only use freedesktop standards (a `.desktop` file, a hicolor icon and AppStream metainfo), so the app appears in the menus of any desktop environment. Building never needs root, except snap in CI.

## Windows formats

A Linux binary does not run on Windows, so Windows formats need a Windows executable (`.exe`) in `[windows]`. On Windows, `[windows] command` runs your usual toolchain. On Linux, most toolchains can cross-compile:

| Toolchain | Command on Linux |
|---|---|
| Wails | `wails build -platform windows/amd64` |
| Go | `GOOS=windows GOARCH=amd64 go build -o build/myapp.exe` |
| Rust | `cargo build --release --target x86_64-pc-windows-gnu` (needs mingw-w64) |

A Python + Qt app can't be frozen into an `.exe` from Linux: build it with PyInstaller on Windows (or on a `windows-latest` CI runner, as [`release.yml`](.github/workflows/release.yml) does for PackagingOnLinux itself).

The architecture (x86, x64, arm64) is read from the executable. Two formats are built from it:

- `zip`: a portable `<Name>-<version>-windows-<arch>.zip`. Unzip it anywhere and run the `.exe`. No tool needed.
- `nsis`: an installer, `<Name>-<version>-windows-<arch>-setup.exe`, made with `makensis` (`apt install nsis`, `dnf install mingw32-nsis`, or NSIS for Windows). It:
  - installs for the current user into `%LOCALAPPDATA%\Programs\<Name>`, without administrator rights;
  - adds a Start menu shortcut, and a desktop one if ticked;
  - registers the app with its uninstaller in Windows' "Apps" settings.

  `setup.exe /S` installs silently.

The installer is not signed, so on first launch Windows SmartScreen warns that the publisher is unknown ("More info" → "Run anyway"). Code signing needs a certificate and is not supported yet.

## CI

The CLI runs unattended: install the tools of the formats you build (or use `--container`), then run `packagingonlinux build`. [`.github/workflows/release.yml`](.github/workflows/release.yml) is a complete example: on a `vX.Y.Z` tag, it builds every format of PackagingOnLinux itself and attaches them to a GitHub release. Reusable GitHub and GitLab templates are planned.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[gui,test]'
QT_QPA_PLATFORM=offscreen .venv/bin/pytest                    # GUI tests run headless
PACKAGINGONLINUX_TEST_CONTAINER=1 .venv/bin/pytest tests/test_container.py   # + a real --container build (Docker)
python3 tools/gen_man.py                                      # regenerate docs/man/packagingonlinux.1 after a CLI change
```

`tests/test_man.py` fails when the generated man page is out of date. `packaging.toml(5)` is written by hand: document every new config key there. With Docker, `packagingonlinux build --container -f rpm` builds and tests rpm packages from a non-rpm distribution.

## License

[GPL-3.0](LICENSE.md)
