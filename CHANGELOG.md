# Changelog

All notable changes to PackagingOnLinux are documented here.
A release is published only for a version that has a section in this file.

## [Unreleased]

### Added
- `build --container`: the Linux build command and formats (all but snap) run in a Docker container, with every packaging tool. It is the default on Windows, so that a Windows machine with Docker Desktop builds the Linux packages too; `--no-container` turns it off. Without Docker, or with Docker stopped, the build stops with an error saying what to do.
- GUI: « Construire dans un conteneur Docker » option above the Linux formats, ticked by default on Windows.
- `doctor` tells whether Docker can be used.
- `-c -` reads the config from standard input.
- `$PACKAGINGONLINUX_CONTAINER_IMAGE` selects another image for `--container`.

### Changed
- On a non-Linux host, without the container, the Linux formats are refused instead of producing broken packages.

## [0.2.0]

### Added
- AppImage format (`appimage`).
- Flatpak format (`flatpak`), with its runtime and sandbox permissions in the new `[flatpak]` section.
- Snap format (`snap`), with its base, confinement and interfaces in the new `[snap]` section.
- PackagingOnLinux itself is released as an AppImage, a Flatpak and a Snap, which include Python and Qt. From the Flatpak, packaging tools run on the host.
- `packagingonlinux --help` lists the formats with the tools they need, examples and exit statuses; the same content is in the `packagingonlinux(1)` man page (`docs/man/`).
- `packaging.toml(5)` man page: every section and key of the config, with types, defaults and examples.
- `man` key in `[linux]` (« Pages de manuel » in the GUI): man pages installed gzipped into `/usr/share/man/man<N>/`. The PackagingOnLinux packages now ship `packagingonlinux(1)` and `packaging.toml(5)`.

## [0.1.3]

### BREAKING CHANGE FOR THE TOML FILE

### Added
- `doctor` prints the PackagingOnLinux version first.
- The GUI keeps a list of recently opened configurations.
- Clicking "Construire les paquets" asks for the release type (fix, minor, major, none) and bumps the version.
- Windows NSIS / portable zip builder
- folder architecture refactor

## [0.1.1]

### Added
- `doctor` prints the PackagingOnLinux version first.
- 

### Fixed
- The app icon shows in the GNOME dock on X11.
