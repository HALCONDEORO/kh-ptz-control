#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# mode_border_overlay.py — Borde de color alrededor de toda la ventana según modo
#
# CALL → verde  |  SET → rojo
# Transición animada de ~300 ms con fundido cruzado de color.
# WA_TransparentForMouseEvents: no intercepta ningún clic.

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import QWidget

_ANIM_INTERVAL_MS = 16
_ANIM_DURATION_MS = 300
_ANIM_STEP        = _ANIM_INTERVAL_MS / _ANIM_DURATION_MS

_BORDER_PX   = 8
_COLOR_CALL  = QColor(184,  74,  74,  220)   # burdeos — igual que call_frame del panel
_COLOR_SET   = QColor( 94, 168,  94,  230)   # verde   — igual que set_frame del panel


class ModeBorderOverlay(QWidget):
    """
    Widget transparente 1920×1080 que dibuja solo el borde exterior con el color
    del modo activo. Siempre visible; animación de color al cambiar de modo.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._mode      = 'call'
        self._prev_mode = 'call'
        self._blend     = 1.0

        self.setGeometry(0, 0, 1920, 1080)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        # WA_TranslucentBackground solo funciona en ventanas top-level; en un
        # child widget no tiene efecto. El centro es transparente porque
        # autoFillBackground permanece False (comportamiento por defecto de QWidget).

        self._timer = QTimer(self)
        self._timer.setInterval(_ANIM_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def set_mode(self, mode: str):
        if mode == self._mode:
            return
        self._prev_mode = self._mode
        self._mode      = mode
        self._blend     = 0.0
        self._timer.start()

    def _tick(self):
        self._blend = min(1.0, self._blend + _ANIM_STEP)
        self.update()
        if self._blend >= 1.0:
            self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._blend >= 1.0:
            self._draw_border(painter, self._mode, 1.0)
        else:
            self._draw_border(painter, self._prev_mode, 1.0 - self._blend)
            self._draw_border(painter, self._mode,      self._blend)

        painter.end()

    def _draw_border(self, painter: QPainter, mode: str, opacity: float):
        base  = _COLOR_CALL if mode == 'call' else _COLOR_SET
        color = QColor(base.red(), base.green(), base.blue(),
                       int(base.alpha() * opacity))
        painter.setPen(Qt.NoPen)
        w, h, b = self.width(), self.height(), _BORDER_PX
        for rect in [
            (0,     0,     w,     b    ),   # top
            (0,     h - b, w,     b    ),   # bottom
            (0,     b,     b,     h-2*b),   # left
            (w - b, b,     b,     h-2*b),   # right
        ]:
            painter.fillRect(*rect, color)
