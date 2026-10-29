#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# widgets.py — Widgets personalizados de la UI
#
# Responsabilidad única: definir componentes visuales reutilizables
# que no contienen lógica de negocio (no saben nada de VISCA ni de presets).
#
# Widgets incluidos:
#   DragDropButton    — clase base con drag-drop y doble-tap compartidos
#   GoButton          — botón de asiento numerado (hereda DragDropButton + QPushButton)
#   SpecialDragButton — QToolButton especial (hereda DragDropButton + QToolButton)
#   NamesListWidget   — QListWidget con reordenamiento interno + arrastre externo
#   NamesPanel        — panel flotante compacto con lista editable de asistentes
#   PresetActionMixin — mixin de interacción para botones de preset (left=CALL, right/long=SET)
#
# CAMBIOS EN ESTE REFACTOR:
#
#   1. DUPLICACIÓN ELIMINADA — nueva clase DragDropButton:
#      GoButton y SpecialDragButton tenían estos 4 métodos idénticos o casi:
#        dragEnterEvent, dragMoveEvent, dropEvent → byte-for-byte idénticos
#        mouseDoubleClickEvent → misma estructura, solo difería el mensaje
#      Se extrae DragDropButton como mixin de comportamiento.
#      Cualquier cambio en lógica de drag (p.ej. filtrar MIME) ahora es
#      una sola edición, no dos.
#      El mensaje del diálogo de confirmación se parametriza via
#      _clear_confirm_msg() — cada subclase lo implementa con su contexto.
#
#   2. FIX PYTHON 3.9: `int | None` → Optional[int] en _dragging_row.
#      MOTIVO: `|` en anotaciones de variables de instancia no está cubierto
#      por `from __future__ import annotations` en Python 3.9.
#
#   3. FIX _apply_assigned_style(): reemplaza str.replace() frágil por
#      concatenación directa del bloque CSS de borde verde al estilo base.
#      La versión anterior fallaba silenciosamente si el estilo base no
#      contenía exactamente 'border: 0px solid black;' o 'border: none;'.

import logging
import math
import os
from typing import ClassVar, Optional  # reemplaza `int | None` (sintaxis 3.10+)

logger = logging.getLogger(__name__)

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt, QPoint, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import (
    QApplication, QGraphicsOpacityEffect, QMessageBox, QPushButton, QToolButton,
)

from config import BUTTON_COLOR

# Comprobación única al arranque — seat.svg es un asset estático
_SEAT_SVG_EXISTS = os.path.exists("seat.svg")
_SEAT_SVG_BG     = (
    "background-image: url(seat.svg); background-repeat: no-repeat; background-position: center;"
    if _SEAT_SVG_EXISTS else ""
)


# ─────────────────────────────────────────────────────────────────────────────
# DragDropButton — mixin de drag-drop y doble-tap compartido
# ─────────────────────────────────────────────────────────────────────────────

class DragDropButton:
    """
    Mixin de comportamiento para botones que aceptan drag-drop de nombres
    desde NamesListWidget y permiten borrar la asignación con doble-tap.

    NO hereda de ningún widget Qt — se combina con QPushButton o QToolButton
    mediante herencia múltiple en GoButton y SpecialDragButton.

    CONTRATO CON SUBCLASES (deben definir):
      self.assigned_name  — str, nombre actualmente asignado ('' = vacío)
      set_name(name: str) — aplica el borrado/asignación
      _clear_confirm_msg()→ str — texto del diálogo de confirmación de borrado

    MOTIVO DE EXTRACCIÓN:
      Los 4 métodos estaban copiados byte-a-byte en GoButton y SpecialDragButton.
      Un cambio (p.ej. filtrar por tipo MIME, cambiar el botón del diálogo)
      antes requería dos ediciones en dos clases distintas.
    """

    _call_mode: bool = True  # compartida por todas las subclases (GoButton, SpecialDragButton)

    # ── Pulso del asiento activo (clase GoButton lo usa) ─────────────────
    _pulse_timer:   Optional[QTimer]    = None
    _pulse_phase:   float               = 0.0
    _pulse_cycles:  int                 = 0
    _active_button: Optional['GoButton'] = None

    def dragEnterEvent(self, event):
        """Acepta drops solo en modo SET. En modo CALL ignora el drag."""
        if self._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self._on_drag_enter()

    def dragMoveEvent(self, event):
        if self._call_mode:
            event.ignore()
            return
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._on_drag_leave()

    def dropEvent(self, event):
        """Al soltar un nombre sobre el botón, lo asigna al asiento (solo en modo SET)."""
        self._on_drag_leave()
        if self._call_mode:
            event.ignore()
            return
        name = event.mimeData().text().strip()
        if name:
            self.set_name(name)
            event.acceptProposedAction()

    def _on_drag_enter(self):
        """Hook: el botón se convierte en target válido. Subclase sobreescribe para resaltar."""

    def _on_drag_leave(self):
        """Hook: el drag salió o terminó. Subclase sobreescribe para restaurar estilo."""

    def mouseDoubleClickEvent(self, event):
        if self._call_mode:
            super().mouseDoubleClickEvent(event)
            return
        if self.assigned_name:
            reply = QMessageBox.question(
                self.parent(), "Clear Assignment",
                self._clear_confirm_msg(),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.set_name("")
        else:
            # Delegar al siguiente en el MRO (QPushButton o QToolButton)
            super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._call_mode or not (event.buttons() & Qt.LeftButton) or not self.assigned_name:
            super().mouseMoveEvent(event)
            return
        if not hasattr(self, '_drag_start_pos') or self._drag_start_pos is None:
            return
        dist = (event.pos() - self._drag_start_pos).manhattanLength()
        if dist < QApplication.startDragDistance():
            return
        self._on_drag_start()
        drag = QtGui.QDrag(self)
        mime = QtCore.QMimeData()
        mime.setText(self.assigned_name)
        drag.setMimeData(mime)
        result = drag.exec_(Qt.MoveAction | Qt.CopyAction)
        if result == Qt.MoveAction:
            self.set_name("")
        else:
            self._on_drag_end()

    def _on_drag_start(self):
        """Hook: empieza arrastre desde este botón. Subclase sobreescribe para feedback visual."""

    def _on_drag_end(self):
        """Hook: arrastre cancelado (no MoveAction). Subclase restaura el estilo normal."""

    def _clear_confirm_msg(self) -> str:
        """
        Texto del diálogo de confirmación de borrado.
        Debe ser implementado por cada subclase con su contexto.
        Falla explícitamente si se olvida implementar.
        """
        raise NotImplementedError(
            f"{type(self).__name__} debe implementar _clear_confirm_msg()")


# ─────────────────────────────────────────────────────────────────────────────
# PresetActionMixin — reusable preset input handler
# ─────────────────────────────────────────────────────────────────────────────

class PresetActionMixin:
    """
    Mixin for preset buttons: left-click/short-tap → CALL, right-click/long-press → SET.

    Integrating:
        class MyPresetButton(PresetActionMixin, QPushButton):
            def __init__(self, preset, call_cb, set_cb, parent=None):
                super().__init__(parent)
                self.init_preset_actions(preset, call_cb, set_cb)

    Long press duration is LONG_PRESS_MS. Movement does NOT cancel the timer —
    touchscreen fingers always drift during a hold; only the 2-second threshold
    discriminates tap from long-press.
    Right-click suppresses the default context menu.
    """

    LONG_PRESS_MS: int = 2000

    def init_preset_actions(
        self,
        preset_number: int,
        call_cb,
        set_cb,
    ) -> None:
        self._preset_number = preset_number
        self._call_cb = call_cb
        self._set_cb = set_cb
        self._long_press_timer = QTimer(self if hasattr(self, 'parent') else None)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.setInterval(self.LONG_PRESS_MS)
        self._long_press_timer.timeout.connect(self._on_long_press)
        self._long_press_fired = False
        self._press_pos: Optional[QPoint] = None

# ── Qt event overrides ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if not hasattr(self, '_long_press_timer'):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.LeftButton:
            self._long_press_fired = False
            self._press_pos = event.pos()
            self._long_press_timer.start()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not hasattr(self, '_long_press_timer'):
            super().mouseReleaseEvent(event)
            return
        if event.button() == Qt.LeftButton:
            self._long_press_timer.stop()
            if not self._long_press_fired:
                self._call_cb(self._preset_number)
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        event.accept()  # suppress default context menu on right-click

    def _on_long_press(self) -> None:
        self._long_press_fired = True
        self._set_cb(self._preset_number)


# ─────────────────────────────────────────────────────────────────────────────
# PlatformPresetButton — botón de plataforma fija (icono + texto)
# ─────────────────────────────────────────────────────────────────────────────

class PlatformPresetButton(PresetActionMixin, QToolButton):
    """Botón de preset de plataforma fija (Left, Right, Platform 2).

    Tap → CALL (recall); pulsación larga / clic derecho → SET (guardar),
    vía PresetActionMixin.init_preset_actions().

    A diferencia de GoButton/SpecialDragButton NO tiene drag-drop ni nombre:
    los presets de plataforma son posiciones fijas, no por persona. Por eso
    tampoco define _apply_style() — conserva el stylesheet que se le asigna.
    """

    def __init__(self, parent=None):
        super().__init__(parent)


# ─────────────────────────────────────────────────────────────────────────────
# GoButton — botón de asiento numerado con drag-drop y nombre asignado
# ─────────────────────────────────────────────────────────────────────────────

class GoButton(PresetActionMixin, DragDropButton, QPushButton):
    """
    Botón de asiento (71×82 px).

    Hereda drag-drop y doble-tap de DragDropButton.
    Hereda el widget Qt de QPushButton.

    SEÑAL name_assigned(int, str):
      (seat_number, name) — name='' borra la asignación.
      MainWindow la conecta para persistir en seat_names.json.

    NOTA: _apply_style() sobreescribe cualquier setStyleSheet() posterior.
    Los botones de plataforma usan QPushButton plano por este motivo.

    ORDEN MRO: DragDropButton primero → sus eventos (drag, doble-tap) tienen
    prioridad. QPushButton aporta __init__, setStyleSheet, etc.
    """

    name_assigned = pyqtSignal(int, str)

    WIDTH  = 71
    HEIGHT = 82

    _spin_angle:    int              = 0
    _spin_timer:    Optional[QTimer] = None
    _saving_buttons: ClassVar[set]   = set()

    def __init__(self, seat_number: int, parent=None):
        # Inicializar QPushButton explícitamente (necesita parent para el árbol Qt)
        QPushButton.__init__(self, str(seat_number), parent)
        self.seat_number    = int(seat_number)  # int explícito: evita bugs si llega str
        self.assigned_name  = ""
        self._preset_state: Optional[str]    = None  # None | "saving" | "saved" | "test_error" | "test_warning"
        self._feedback_timer: Optional[QTimer] = None
        self._preset_pending: bool           = False
        self.resize(self.WIDTH, self.HEIGHT)
        self.setAcceptDrops(True)
        self._apply_style()

    def _clear_confirm_msg(self) -> str:
        """Mensaje con el número de asiento — implementación requerida por DragDropButton."""
        return f'Clear "{self.assigned_name}" from seat {self.seat_number}?'

    # ── Pulso del asiento activo ──────────────────────────────────────────

    @classmethod
    def set_call_mode(cls, call: bool):
        DragDropButton._call_mode = call
        if not call and cls._active_button is not None:
            cls._active_button._deactivate()

    @classmethod
    def _ensure_pulse_timer(cls):
        if cls._pulse_timer is None:
            # Sin parent Qt: el timer vive mientras GoButton (clase) exista.
            # Un único timer de clase dirige todas las instancias activas.
            cls._pulse_timer = QTimer()
            cls._pulse_timer.setInterval(30)
            cls._pulse_timer.timeout.connect(cls._advance_pulse)
            cls._pulse_timer.start()

    @classmethod
    def _advance_pulse(cls):
        new_phase = cls._pulse_phase + 0.035
        if new_phase >= 1.0:
            cls._pulse_cycles += 1
            if cls._pulse_cycles >= 3 and cls._active_button is not None:
                cls._active_button._deactivate()
                return
        cls._pulse_phase = new_phase % 1.0
        if cls._active_button is not None:
            cls._active_button.update()

    def activate(self):
        GoButton._ensure_pulse_timer()
        if GoButton._active_button is not None and GoButton._active_button is not self:
            GoButton._active_button._deactivate()
        GoButton._active_button = self
        GoButton._pulse_phase = 0.0
        GoButton._pulse_cycles = 0
        self.update()

    def _deactivate(self):
        if GoButton._active_button is self:
            GoButton._active_button = None
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._call_mode:
            self.activate()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if GoButton._active_button is self:
            alpha = int(90 + 110 * math.sin(GoButton._pulse_phase * 2 * math.pi))
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            pen = QPen(QColor(255, 210, 60, alpha), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, 4, 4)
            painter.end()
        if self._preset_pending:
            self._draw_pending_border()
        elif self._preset_state == "saving":
            self._draw_saving_overlay()
        elif self._preset_state == "saved":
            self._draw_saved_overlay()
        elif self._preset_state == "test_error":
            self._draw_test_error_overlay()
        elif self._preset_state == "test_warning":
            self._draw_test_warning_overlay()

    def _draw_pending_border(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(46, 125, 50, 45))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        pen = QPen(QColor(46, 125, 50, 255), 3)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, 4, 4)
        painter.end()

    # ── Feedback visual de guardado de preset ────────────────────────────

    def show_saving(self):
        if self._feedback_timer is not None:
            self._feedback_timer.stop()
        self._preset_state = "saving"
        GoButton._saving_buttons.add(self)
        GoButton._ensure_spin_timer()
        # Seguridad: resetear si PRESET_SAVED nunca llega (ej. fallo VISCA)
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._reset_preset_state)
        self._feedback_timer.start(10_000)
        self.update()

    def show_saved(self):
        if self._feedback_timer is not None:
            self._feedback_timer.stop()
        self._preset_state = "saved"
        GoButton._saving_buttons.discard(self)
        if not GoButton._saving_buttons and GoButton._spin_timer is not None:
            GoButton._spin_timer.stop()
        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.timeout.connect(self._reset_preset_state)
        self._feedback_timer.start(2_000)
        self.update()

    def _reset_preset_state(self):
        self._preset_state = None
        self._feedback_timer = None
        GoButton._saving_buttons.discard(self)
        self.update()

    @classmethod
    def _ensure_spin_timer(cls):
        if cls._spin_timer is None:
            cls._spin_timer = QTimer()
            cls._spin_timer.setInterval(30)
            cls._spin_timer.timeout.connect(cls._advance_spin)
        if not cls._spin_timer.isActive():
            cls._spin_timer.start()

    @classmethod
    def _advance_spin(cls):
        cls._spin_angle = (cls._spin_angle + 8) % 360
        for btn in list(cls._saving_buttons):
            btn.update()

    def _draw_saving_overlay(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        cx, cy = self.width() // 2, self.height() // 2
        r = 11
        pen = QPen(QColor(255, 255, 255, 230), 2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        start = (-GoButton._spin_angle) * 16
        span  = 270 * 16
        painter.drawArc(cx - r, cy - r, r * 2, r * 2, start, span)
        painter.end()

    def _draw_saved_overlay(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(46, 125, 50, 200))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        cx, cy = self.width() // 2, self.height() // 2
        pen = QPen(QColor(255, 255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(cx - 9,  cy + 1)
        path.lineTo(cx - 2,  cy + 8)
        path.lineTo(cx + 10, cy - 7)
        painter.drawPath(path)
        painter.end()

    def _draw_test_error_overlay(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(192, 20, 31, 200))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        cx, cy = self.width() // 2, self.height() // 2
        pen = QPen(QColor(255, 255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        d = 8
        painter.drawLine(cx - d, cy - d, cx + d, cy + d)
        painter.drawLine(cx + d, cy - d, cx - d, cy + d)
        painter.end()

    def _draw_test_warning_overlay(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(230, 162, 0, 200))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        cx, cy = self.width() // 2, self.height() // 2
        pen = QPen(QColor(255, 255, 255, 255), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(cx, cy - 8, cx, cy + 2)
        painter.drawPoint(cx, cy + 7)
        painter.end()

    def show_test_result(self, status: str) -> None:
        """Highlight the button during/after a preset test run.

        status: "active"   → pulsing yellow border (being tested now)
                "ok"       → green checkmark overlay, 2 s
                "warning"  → amber overlay with ! (callable, no PTZ metadata), 2 s
                "error"    → red X overlay, 2 s
                otherwise  → clear any test highlight
        """
        if status == "active":
            self.activate()
        elif status == "ok":
            self.show_saved()
        elif status == "warning":
            if self._feedback_timer is not None:
                self._feedback_timer.stop()
            self._preset_state = "test_warning"
            self._feedback_timer = QTimer(self)
            self._feedback_timer.setSingleShot(True)
            self._feedback_timer.timeout.connect(self._reset_preset_state)
            self._feedback_timer.start(2_000)
            self.update()
        elif status == "error":
            if self._feedback_timer is not None:
                self._feedback_timer.stop()
            self._preset_state = "test_error"
            self._feedback_timer = QTimer(self)
            self._feedback_timer.setSingleShot(True)
            self._feedback_timer.timeout.connect(self._reset_preset_state)
            self._feedback_timer.start(2_000)
            self.update()
        else:
            self._deactivate()
            self._reset_preset_state()

    def _apply_style(self):
        """
        Call mode : burdeo pastel vacío / burdeo oscuro si tiene nombre.
        Set mode  : gris, borde verde si tiene nombre.
        Usa seat.svg como fondo si existe; falla silenciosamente a color sólido.
        """
        if self._call_mode:
            svg = "seat_occupied.svg" if self.assigned_name else "seat_call.svg"
            bg = f"background-image: url({svg}); background-repeat: no-repeat; background-position: center;"
            border = "border: none;"
            text_color = "white" if self.assigned_name else BUTTON_COLOR
        elif _SEAT_SVG_EXISTS:
            bg = _SEAT_SVG_BG
            border = (
                "border: 2px solid #2e7d32; border-radius: 4px; background-color: rgba(76,175,80,30);"
                if self.assigned_name else "border: none;"
            )
            text_color = BUTTON_COLOR
        else:
            bg = "background-color: #cccccc;"
            border = (
                "border: 2px solid #2e7d32; border-radius: 4px; background-color: rgba(76,175,80,30);"
                if self.assigned_name else "border: none;"
            )
            text_color = BUTTON_COLOR
        self.setStyleSheet(
            f"QPushButton {{ {bg} {border} font: 12px; font-weight: bold; color: {text_color}; }}"
            f"QPushButton:pressed {{ background-color: rgba(0,0,0,70); }}"
        )

    _DROP_TARGET_STYLE = (
        f"QPushButton {{ {_SEAT_SVG_BG} background-color: rgba(25,118,210,40);"
        f" border: 2px solid #1976D2; border-radius: 4px;"
        f" font: 12px; font-weight: bold; color: {BUTTON_COLOR}; }}"
        f"QPushButton:pressed {{ background-color: rgba(0,0,0,70); }}"
    )
    _DRAG_SOURCE_STYLE = (
        "QPushButton { background-color: rgba(180,180,180,60);"
        " border: 1px dashed #AAAAAA; border-radius: 4px;"
        " font: 12px; font-weight: bold; color: rgba(80,80,80,160); }"
    )

    def _on_drag_enter(self):
        self.setStyleSheet(self._DROP_TARGET_STYLE)

    def _on_drag_leave(self):
        self._apply_style()

    def _on_drag_start(self):
        self.setStyleSheet(self._DRAG_SOURCE_STYLE)

    def _on_drag_end(self):
        self._apply_style()

    def set_name(self, name: str, emit_signal: bool = True):
        """
        Asigna o borra el nombre del asiento.

        emit_signal=False durante el arranque (_restore_seat_names) para
        no disparar guardados al cargar datos ya persistidos.
        """
        self.assigned_name = name
        self.setText(name.split()[0] if name else str(self.seat_number))
        self._apply_style()
        if emit_signal:
            self.name_assigned.emit(self.seat_number, name)

    def set_preset_pending(self, pending: bool) -> None:
        self._preset_pending = pending
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        if dimmed:
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.22)
            self.setGraphicsEffect(eff)
        else:
            self.setGraphicsEffect(None)


# ─────────────────────────────────────────────────────────────────────────────
# SpecialDragButton — QToolButton con drag-drop para botones especiales
# ─────────────────────────────────────────────────────────────────────────────

class SpecialDragButton(PresetActionMixin, DragDropButton, QToolButton):
    """
    QToolButton para botones especiales: Wheelchair (128), Second Room (129),
    Chairman (preset 1).

    Hereda drag-drop y doble-tap de DragDropButton.
    Hereda el widget Qt de QToolButton (necesario para icono arriba + texto abajo).

    DIFERENCIA CON GoButton:
      set_name() muestra el nombre truncado reemplazando _default_label,
      no un número de asiento.

    SEÑAL name_assigned(int, str):
      (seat_id, name). seat_id es la clave en seat_names.json. name='' = borrado.

    ORDEN MRO: DragDropButton primero → sus eventos tienen prioridad.
    QToolButton aporta el widget Qt subyacente.
    """

    name_assigned = pyqtSignal(int, str)

    def __init__(self, seat_id: int, default_label: str, parent=None):
        QToolButton.__init__(self, parent)
        self.seat_number    = seat_id
        self._default_label = default_label
        self.assigned_name  = ""
        self._preset_pending: bool = False
        self.setText(default_label)
        self.setAcceptDrops(True)

    def _clear_confirm_msg(self) -> str:
        return f'Clear "{self.assigned_name}" from {self._default_label}?'

    def _apply_style(self):
        """
        Call mode : burdeo pastel vacío / burdeo oscuro con nombre (igual que GoButton).
        Set mode  : gris con borde marrón vacío / borde verde con nombre.
        """
        if self._call_mode:
            if self.assigned_name:
                style = (
                    "background-color: #8c3048; border: none; border-radius: 5px;"
                    " font: 8px; font-weight: bold; color: white;"
                )
            else:
                style = (
                    f"background-color: #e8b4bc; border: none; border-radius: 5px;"
                    f" font: 8px; font-weight: bold; color: {BUTTON_COLOR};"
                )
        else:
            if self.assigned_name:
                style = (
                    "background-color: rgba(76,175,80,30); border: 2px solid #2e7d32;"
                    f" border-radius: 5px; font: 8px; font-weight: bold; color: {BUTTON_COLOR};"
                )
            else:
                style = (
                    "background-color: #cccccc; border: 2px solid #7B4F2E;"
                    f" border-radius: 5px; font: 8px; font-weight: bold; color: {BUTTON_COLOR};"
                )
        self.setStyleSheet(f"QToolButton {{ {style} }}")

    def set_name(self, name: str, emit_signal: bool = True):
        self.assigned_name = name
        self.setText(name.split()[0] if name else self._default_label)
        self._apply_style()
        if emit_signal:
            self.name_assigned.emit(self.seat_number, name)

    def set_preset_pending(self, pending: bool) -> None:
        self._preset_pending = pending
        self.update()

    def set_dimmed(self, dimmed: bool) -> None:
        if dimmed:
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.22)
            self.setGraphicsEffect(eff)
        else:
            self.setGraphicsEffect(None)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._preset_pending:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(46, 125, 50, 45))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(0, 0, self.width(), self.height(), 5, 5)
            pen = QPen(QColor(46, 125, 50, 255), 3)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(2, 2, self.width() - 4, self.height() - 4, 5, 5)
            painter.end()
