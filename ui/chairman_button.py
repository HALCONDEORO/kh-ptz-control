#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# chairman_button.py — Widget del botón Chairman con preset por persona
#
# FLUJO CON EVENTBUS:
#   Antes:  set_name() → on_recall_cb(preset_num)  [callback directo a MainWindow]
#   Ahora:  set_name() → bus.emit(CHAIRMAN_ASSIGNED, name=name)
#           Controller suscribe CHAIRMAN_ASSIGNED → PresetService → CameraPort
#
#   Antes:  _on_save_clicked() → on_save_cb(name)  [callback a MainWindow]
#   Ahora:  _on_save_clicked() → bus.emit(PRESET_SAVE_REQUESTED, camera=1, name=name)
#           Controller suscribe PRESET_SAVE_REQUESTED → PresetService.assign_slot() → CameraPort
#
#   _update_aux_buttons() sigue leyendo _preset_svc.has_preset(name) para el display.
#   NO hay dependencia de dict mutable compartido; PresetService es la única fuente.

from __future__ import annotations

import re

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import QPushButton

from ui.widgets import SpecialDragButton
from core.events import AsyncEventBus, EventType


class ChairmanButton(SpecialDragButton):
    """
    Botón Chairman con gestión de preset por persona.

    Parámetros:
      bus          — AsyncEventBus del sistema (emite CHAIRMAN_ASSIGNED y PRESET_SAVE_REQUESTED)
      preset_svc   — PresetService (solo lectura, para display de botones auxiliares)
      svg_data     — datos SVG del icono
    """

    _AUX_Y   = 150
    _AUX_CX  = 744
    _SAVE_W  = 110
    _SAVE_H  = 28
    _EDIT_W  = 52
    _EDIT_H  = 28

    def __init__(self, bus: AsyncEventBus, preset_svc,
                 svg_data: str, icon_w: int, icon_h: int, parent=None):
        super().__init__(seat_id=1, default_label='Chairman', parent=parent)

        self._bus        = bus
        self._preset_svc = preset_svc
        self._bus.subscribe_qt(EventType.PRESET_SAVED, self._on_preset_saved_event)

        renderer = QSvgRenderer(QtCore.QByteArray(svg_data.encode('utf-8')))
        pix = QPixmap(icon_w, icon_h)
        pix.fill(Qt.transparent)
        painter = QtGui.QPainter(pix)
        renderer.render(painter, QtCore.QRectF(0, 0, icon_w, icon_h))
        painter.end()
        self.setIcon(QIcon(pix))
        self.setIconSize(QtCore.QSize(icon_w, icon_h))
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setStyleSheet(
            "QToolButton {"
            "  background-color: transparent; border: none;"
            "  font: bold 13px; color: black;"
            "}"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )

        self._btn_save = QPushButton('💾 Save position', parent)
        self._btn_save.setGeometry(
            self._AUX_CX - self._SAVE_W // 2, self._AUX_Y,
            self._SAVE_W, self._SAVE_H
        )
        self._btn_save.clicked.connect(self._on_save_clicked)
        self._btn_save.hide()

        self._btn_edit = QPushButton('✏ Edit', parent)
        self._btn_edit.setGeometry(
            self._AUX_CX - self._EDIT_W // 2, self._AUX_Y,
            self._EDIT_W, self._EDIT_H
        )
        self._btn_edit.clicked.connect(self._on_edit_clicked)
        self._btn_edit.hide()

        self._update_aux_buttons()

    # ── Override de _apply_style ─────────────────────────────────────────

    def _apply_style(self):
        super()._apply_style()
        # Agrandar fuente del nombre chairman (regex: tolerante a variaciones de px o espacios)
        self.setStyleSheet(
            re.sub(r'font:\s*[^;]+;(\s*font-weight:\s*[^;]+;)?', 'font: bold 13px;', self.styleSheet())
        )
        self._update_aux_buttons()

    def _refresh_aux_style(self):
        save_style = (
            "QPushButton { background: #1976D2; border: none; border-radius: 4px;"
            " font: bold 11px; color: white; }"
            "QPushButton:pressed { background: #1255a0; }"
        )
        edit_style = (
            "QPushButton { background: rgba(80,80,80,180); border: none; border-radius: 4px;"
            " font: 10px; color: #ddd; }"
            "QPushButton:pressed { background: rgba(50,50,50,200); }"
        )
        self._btn_save.setStyleSheet(save_style)
        self._btn_edit.setStyleSheet(edit_style)

    # ── Override de set_name ──────────────────────────────────────────────

    def set_name(self, name: str, emit_signal: bool = True):
        """
        emit_signal=False durante _restore_seat_names (arranque).
        En ese caso no se emite CHAIRMAN_ASSIGNED → cámara no se mueve.
        """
        super().set_name(name, emit_signal=emit_signal)

        if name and emit_signal:
            self._bus.emit(EventType.CHAIRMAN_ASSIGNED, name=name)

        self._update_aux_buttons()

    def _update_aux_buttons(self):
        name = self.assigned_name
        if not name or self._call_mode:
            self._btn_save.hide()
            self._btn_edit.hide()
            return

        self._refresh_aux_style()
        has_preset = self._preset_svc.has_preset(name)
        if has_preset:
            self._btn_save.hide()
            self._btn_edit.show()
            self._btn_edit.raise_()
        else:
            self._btn_save.show()
            self._btn_save.raise_()
            self._btn_edit.hide()

    def _on_edit_clicked(self):
        self._btn_edit.hide()
        self._btn_save.show()
        self._btn_save.raise_()

    def request_person_save(self) -> None:
        """Public: save the assigned person's preset (same as the 💾 button).

        Used by the long-press SET gesture on the Chairman platform button.
        No-op when no person is assigned.
        """
        self._on_save_clicked()

    def _on_save_clicked(self):
        name = self.assigned_name
        if not name:
            return
        self._bus.emit(EventType.PRESET_SAVE_REQUESTED, camera=1, name=name)
        # No actualizar UI aquí: esperamos el evento PRESET_SAVED.
        # Si el Save VISCA falla, el evento no se emite y Save queda visible para reintentar.

    def _on_preset_saved_event(self, event) -> None:
        """Refresca botones solo cuando el preset guardado corresponde a la persona asignada."""
        if event.payload.get("name") == self.assigned_name:
            self._update_aux_buttons()
