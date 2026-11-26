# Changelog

All notable changes to PackagingOnLinux are documented here.
A release is published only for a version that has a section in this file.

## [Unreleased]

### Added
- `--version VERSION` option of `build` and `check`: replaces `[app] version` (and `$APP_VERSION` of the build command) without editing packaging.toml, e.g. with the version of a release tag in CI.
- Reusable GitHub workflow `.github/workflows/package.yml`: other repositories build the packages of their packaging.toml with `uses: Spatulox/PackagingOnLinux/.github/workflows/package.yml@v0` and get them as `release-*` artifacts, ready for release-kit. It installs the tools of the requested formats, builds every format but snap on one runner and the snap on the Ubuntu release of `[snap] base`. The `v0` tag follows the latest stable release.

### Fixed
- Started from the desktop menu, the GUI did not find build tools that only the user's shell startup files add to `PATH` (e.g. `wails` in `~/go/bin`, `npm` from nvm): build commands failed with exit 127. It now loads the environment of the login shell (`$SHELL -ilc`) at startup when it is not run from a terminal, and always from the Flatpak (for the commands it runs on the host). `PACKAGINGONLINUX_NO_SHELL_ENV=1` turns this off.

### Changed
- PackagingOnLinux is released with release-kit: tags `vX.Y.Z_alpha`, `_beta`, `_rc` publish pre-releases, and "Run workflow" in the Actions tab builds every package without publishing anything.

## [0.3.1]

### Added
- Weak dependencies in `[deps]`: `deb_recommends` and `deb_suggests` fill the deb `Recommends` and `Suggests` fields, `rpm_recommends` and `rpm_suggests` the rpm `Recommends:` and `Suggests:` tags (« Recommandées » / « Suggérées » in the GUI). An rpm dependency written with `a | b` is rejected: rpm needs `(a or b)`.
- `wm_class` key in `[linux]` (« WM_CLASS de la fenêtre » in the GUI): written as `StartupWMClass` in the `.desktop` file of every Linux format, so that the desktop links the app's windows to its launcher when they announce another name than the app id.
- `autostart` and `autostart_args` keys in `[linux]` and `[windows]` (« Démarrage automatique » in the GUI): start the app, with these arguments, when the user signs in. deb, rpm and tar.gz install an XDG autostart entry, `/etc/xdg/autostart/<id>.desktop` (a conffile / `%config`); the Windows installer gets a « Lancer à l'ouverture de session » check box, checked by default, that writes the user's `Run` registry key. AppImage, Flatpak, Snap and the Windows zip install nothing system-wide and ignore it, with a warning. `check` also validates the autostart entry.

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
