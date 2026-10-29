#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# seat_builder.py — Factory para botones de asientos especiales
#
# Centraliza la creación de los 4 asientos especiales (128-131) que antes
# tenían bloques if/elif repetidos en main_window._build_seat_buttons().
#
# API pública:
#   build_special_seat_button(seat_number, x, y, parent) → SpecialDragButton
#
# Las señales (name_assigned, clicked) NO se conectan aquí — las conecta
# MainWindow inmediatamente después de recibir el botón.

from __future__ import annotations

import logging
from typing import Optional

from PyQt5 import QtCore, QtGui

logger = logging.getLogger(__name__)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtSvg import QSvgRenderer

from ui.widgets import SpecialDragButton
from ui.platform_icons import SVG_WHEELCHAIR


# ── Definiciones por asiento ──────────────────────────────────────────────────
# svg_data : string SVG embebido (tiene prioridad sobre svg_file)
# svg_file : ruta a archivo .svg (se usa si svg_data es None)

_SPECIAL_SEAT_DEFS = {
    128: dict(label='Wheelchair',  svg_data=SVG_WHEELCHAIR, svg_file=None,              w=55, h=65, iw=40, ih=40),
    129: dict(label='2nd Room', svg_data=None,           svg_file='second_room.svg', w=55, h=65, iw=40, ih=40),
    130: dict(label='Wheelchair',  svg_data=SVG_WHEELCHAIR, svg_file=None,              w=55, h=65, iw=40, ih=40),
    131: dict(label='Library',     svg_data=None,           svg_file='library.svg',     w=55, h=65, iw=40, ih=40),
}

# ── API pública ───────────────────────────────────────────────────────────────

def build_special_seat_button(seat_number: int, x: int, y: int, parent) -> SpecialDragButton:
    """
    Crea, dimensiona, estiliza y pone icono en un SpecialDragButton.
    NO conecta señales — el llamador (MainWindow) las conecta tras recibir el botón.
    """
    defn = _SPECIAL_SEAT_DEFS[seat_number]
    button = SpecialDragButton(seat_id=seat_number, default_label=defn['label'], parent=parent)
    button.move(x, y)
    button.resize(defn['w'], defn['h'])
    button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
    button._apply_style()

    pix = _load_svg_pixmap(defn['svg_data'], defn['svg_file'], defn['iw'], defn['ih'])
    if pix is not None:
        button.setIcon(QtGui.QIcon(pix))
        button.setIconSize(QtCore.QSize(defn['iw'], defn['ih']))

    return button


# ── Helper privado ────────────────────────────────────────────────────────────

def _load_svg_pixmap(svg_data: Optional[str], svg_file: Optional[str],
                     w: int, h: int) -> Optional[QPixmap]:
    """Renderiza SVG a QPixmap. Devuelve None si no hay fuente válida."""
    if svg_data:
        renderer = QSvgRenderer(QtCore.QByteArray(svg_data.encode('utf-8')))
    elif svg_file:
        renderer = QSvgRenderer(svg_file)
        if not renderer.isValid():
            logger.warning("%s no encontrado o inválido", svg_file)
            return None
    else:
        return None

    if not renderer.isValid():
        return None

    pix = QPixmap(w, h)
    pix.fill(Qt.transparent)
    painter = QtGui.QPainter(pix)
    renderer.render(painter, QtCore.QRectF(0, 0, w, h))
    painter.end()
    return pix
