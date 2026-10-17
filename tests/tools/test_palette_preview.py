"""T012 — the G1 palette preview tool renders a full sheet (pytest-qt smoke)."""

from pathlib import Path

from PySide6.QtGui import QImage

from tools.palette_preview import render


def test_preview_sheet_renders(qapp, tmp_path: Path):
    out = tmp_path / "preview.png"
    render(out, "#3B82F6")
    image = QImage(str(out))
    # 6 panels in 3 columns: width 3*520 + 4*24 = 1656; height 2*(260 + 28) + 3*24 = 648.
    assert (image.width(), image.height()) == (1656, 648)
