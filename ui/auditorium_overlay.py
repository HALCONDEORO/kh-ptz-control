#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# auditorium_overlay.py — Overlay semitransparente del panel izquierdo
#
# Dos modos visuales:
#   'set'  → relleno blanco semitransparente
#   'call' → pequeños puntos blancos sobre fondo transparente
#
# El cambio de modo usa fundido cruzado de ~220 ms.
# El grid de puntos se renderiza una sola vez en QPixmap (GPU blit en cada frame).

# PEP 604 unions (`X | None`) en anotaciones requieren Python 3.10+ si se
# evalúan en runtime; en Python 3.9.2 (Raspberry Pi OS Bullseye) romperían al
# importar. Anotaciones diferidas → se guardan como cadenas. Primer import.
from __future__ import annotations

from PyQt5.QtCore import Qt, QPointF, QTimer
from PyQt5.QtGui import QColor, QPainter, QBrush, QPixmap
from PyQt5.QtWidgets import QWidget

_ANIM_INTERVAL_MS = 16
_ANIM_DURATION_MS = 220
_ANIM_STEP        = _ANIM_INTERVAL_MS / _ANIM_DURATION_MS

_DOT_COLOR   = QColor(255, 255, 255, 55)
_FILL_COLOR  = QColor(255, 255, 255, 55)
_DOT_RADIUS  = 2
_DOT_SPACING = 24


class AuditoriumOverlay(QWidget):
    """
    Widget transparente que cubre todo el panel izquierdo (0,0 → 1490,1080).
    Siempre visible; cambia su apariencia según el modo activo con fundido cruzado.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._mode      = 'call'
        self._prev_mode = 'call'
        self._blend     = 1.0

        self.setGeometry(0, 0, 1490, 1080)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._dot_pixmap: QPixmap | None = None

        self._timer = QTimer(self)
        self._timer.setInterval(_ANIM_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def set_mode(self, mode: str):
        """'call' → puntos blancos  |  'set' → relleno blanco claro"""
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

    def _ensure_dot_pixmap(self):
        if self._dot_pixmap is not None:
            return
        px = QPixmap(self.size())
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(_DOT_COLOR))
        x = _DOT_SPACING // 2
        while x < px.width():
            y = _DOT_SPACING // 2
            while y < px.height():
                p.drawEllipse(QPointF(x, y), _DOT_RADIUS, _DOT_RADIUS)
                y += _DOT_SPACING
            x += _DOT_SPACING
        p.end()
        self._dot_pixmap = px

    # ── pintado ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._blend >= 1.0:
            self._draw_mode(painter, self._mode, 1.0)
        else:
            self._draw_mode(painter, self._prev_mode, 1.0 - self._blend)
            self._draw_mode(painter, self._mode,      self._blend)

        painter.end()

    def _draw_mode(self, painter: QPainter, mode: str, opacity: float):
        painter.setOpacity(opacity)
        if mode == 'set':
            painter.fillRect(self.rect(), _FILL_COLOR)
        else:
            self._ensure_dot_pixmap()
            painter.drawPixmap(0, 0, self._dot_pixmap)
