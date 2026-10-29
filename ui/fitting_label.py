# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Title label with shrink-to-fit display font.

Fallback fonts are often wider than the designed family, so a fixed point
size can clip at both edges (seen on the splash title, whose column is
fixed at 620px). Kept out of ui/widgets.py so light consumers (splash)
do not inherit that module's heavier imports.
"""

from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QLabel


def fit_label_font_to_width(text: str, family: str, max_pt: int, min_pt: int,
                            avail_px: int) -> QFont:
    """Return a bold QFont shrunk from max_pt until text fits avail_px."""
    font = QFont(family, max_pt, QFont.Bold)
    while font.pointSize() > min_pt and \
            QFontMetrics(font).horizontalAdvance(text) > avail_px:
        font.setPointSize(font.pointSize() - 2)
    return font


class FittingTitleLabel(QLabel):
    """Title label that re-fits its font to its own width on every resize."""

    def __init__(self, text: str, family: str = 'Inter Tight',
                 max_pt: int = 52, min_pt: int = 20, parent=None) -> None:
        super().__init__(text, parent)
        self._fit_family = family
        self._fit_max_pt = max_pt
        self._fit_min_pt = min_pt
        self.setFont(QFont(family, max_pt, QFont.Bold))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        self.setFont(fit_label_font_to_width(
            self.text(), self._fit_family, self._fit_max_pt,
            self._fit_min_pt, int(self.width() * 0.98)))
