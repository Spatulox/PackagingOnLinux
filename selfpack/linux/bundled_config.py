"""Write build/packaging-bundled.toml, the config of the AppImage, Flatpak and Snap of
PackagingOnLinux.

Those formats can't rely on the system's Python and PyQt6 like the deb and rpm do: they
package the PyInstaller bundle in build/linux/packagingonlinux/ instead (Python and Qt
included, made by the release workflow). The generated config is the root packaging.toml
(same metadata, version, [flatpak] and [snap] options) with that bundle as [linux] target.

Usage, from the repository root, once the bundle exists:
    python3 selfpack/linux/bundled_config.py
    python3 -m packagingonlinux build -c build/packaging-bundled.toml -f appimage,flatpak,snap
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from packagingonlinux import config  # noqa: E402

BUNDLE = ROOT / "build/linux/packagingonlinux"
OUTPUT = ROOT / "build/packaging-bundled.toml"


def main() -> None:
    spec = config.load(ROOT / "packaging.toml")
    spec.linux = config.Target(dir=BUNDLE, exec="packagingonlinux", icon=spec.linux.icon)
    spec.windows = None
    spec.formats = ["appimage", "flatpak", "snap"]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    config.save(spec, OUTPUT)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
