"""Regenerate selfpack/packagingonlinux.ico (used by the Windows packages) from the SVG.

Usage: python selfpack/windows/make_icon.py   (needs PySide6 and Pillow)
"""

import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

SELFPACK = Path(__file__).resolve().parent.parent
SVG = SELFPACK / "packagingonlinux.svg"
ICO = SELFPACK / "packagingonlinux.ico"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main() -> None:
    app = QGuiApplication(["make_icon", "-platform", "offscreen"])  # noqa: F841
    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        raise SystemExit(f"cannot read {SVG}")
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buf, "PNG")
    Image.open(io.BytesIO(bytes(buf.data()))).save(ICO, sizes=[(s, s) for s in SIZES])
    print(f"wrote {ICO}")


if __name__ == "__main__":
    main()
