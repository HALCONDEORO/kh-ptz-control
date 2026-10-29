#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# camera_indicator.py — Indicador visual de cámara activa (cono de luz / spotlight)
#
# CameraIndicator es un widget transparente sin interacción que dibuja
# un cono de luz naranja parpadeante:
#
#   Platform (Cam1):  lámpara justo debajo del asiento 116 → cono apunta
#                     hacia arriba (ilumina la plataforma).
#   Comments (Cam2):  lámpara a nivel de la plataforma → cono apunta
#                     hacia abajo (ilumina la zona de comentarios/asientos).
#
# USO en MainWindow:
#   self._cam_indicator = CameraIndicator(self)
#   self._cam_indicator.set_mode('platform')   # o 'comments'

from PyQt5.QtCore import Qt, QPointF, QTimer
from PyQt5.QtGui import (
    QPainter, QColor, QLinearGradient, QRadialGradient,
    QPolygonF, QBrush,
)
from PyQt5.QtWidgets import QWidget

# Geometrías según modo
_GEO_PLATFORM = (559, 845, 340, 90)   # asiento 116: +20 px derecha, +20 px abajo
_GEO_COMMENTS = (574, 155, 340, 90)   # franja plataforma: +20 px abajo


class CameraIndicator(QWidget):
    """
    Widget transparente que dibuja un spotlight naranja parpadeante
    indicando qué cámara está activa.

    No captura eventos de ratón (WA_TransparentForMouseEvents).
    """

    _BLINK_TOGGLES = 6   # 3 parpadeos completos (on→off = 1 toggle × 2 por parpadeo)

    def __init__(self, parent):
        super().__init__(parent)
        self._mode = 'platform'
        self._blink_on  = True
        self._blink_count = 0

        self.setGeometry(*_GEO_PLATFORM)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle_blink)
        self._timer.start(500)

    def _toggle_blink(self):
        self._blink_count += 1
        self._blink_on = not self._blink_on
        if self._blink_count >= self._BLINK_TOGGLES:
            self._timer.stop()
            self._blink_on = True   # queda fijo encendido
        self.update()

    def _restart_blink(self):
        """Reinicia la secuencia de parpadeo al cambiar de modo."""
        self._timer.stop()
        self._blink_on    = True
        self._blink_count = 0
        self._timer.start(500)

    def set_mode(self, mode: str):
        """
        Cambia la dirección del cono, reposiciona el widget y redibuja.
        mode: 'platform'  → lámpara abajo del asiento 116, cono hacia arriba
              'comments'  → lámpara en zona de plataforma, cono hacia abajo
        """
        self._mode = mode
        geo = _GEO_PLATFORM if mode == 'platform' else _GEO_COMMENTS
        self.setGeometry(*geo)
        self._restart_blink()

    # ── Dibujo ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        if not self._blink_on:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx = w // 2

        if self._mode == 'platform':
            # Lámpara en la parte inferior (asientos), cono apunta hacia arriba.
            lamp      = QPointF(cx, h - 10)
            base_y    = 6
            half_open = 155
        else:
            # Lámpara en la parte superior (plataforma), cono apunta hacia abajo.
            lamp      = QPointF(cx, 10)
            base_y    = h - 6
            half_open = 155

        base_l = QPointF(cx - half_open, base_y)
        base_r = QPointF(cx + half_open, base_y)

        # ── Cono de luz — naranja tenue ───────────────────────────────────
        cone = QPolygonF([lamp, base_l, base_r])

        grad = QLinearGradient(lamp, QPointF(cx, base_y))
        grad.setColorAt(0.0, QColor(255, 120,   0,  60))
        grad.setColorAt(0.5, QColor(255, 150,   0,  28))
        grad.setColorAt(1.0, QColor(255, 165,   0,   0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(cone)

        # ── Halo de la lámpara — naranja suave ───────────────────────────
        glow_r = 14
        glow = QRadialGradient(lamp, glow_r)
        glow.setColorAt(0.0, QColor(255, 120,   0, 110))
        glow.setColorAt(0.6, QColor(255, 140,   0,  45))
        glow.setColorAt(1.0, QColor(255, 165,   0,   0))

        painter.setBrush(QBrush(glow))
        painter.drawEllipse(lamp, glow_r, glow_r)

        # ── Núcleo de la lámpara — naranja brillante ──────────────────────
        core_r = 6
        core = QRadialGradient(lamp, core_r)
        core.setColorAt(0.0, QColor(255, 200,  80, 230))
        core.setColorAt(1.0, QColor(255, 120,   0, 140))

        painter.setBrush(QBrush(core))
        painter.drawEllipse(lamp, core_r, core_r)

        painter.end()
