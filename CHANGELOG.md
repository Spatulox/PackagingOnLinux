# Changelog

All notable changes to PackagingOnLinux are documented here.
A release is published only for a version that has a section in this file.

## [Unreleased]

### Added
- AppImage format (`appimage`).
- Flatpak format (`flatpak`), with its runtime and sandbox permissions in the new `[flatpak]` section.

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
