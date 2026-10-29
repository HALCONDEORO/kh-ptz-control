#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# right_panel.py — Panel derecho de controles PTZ (layout-based)
#
# Todos los widgets viven dentro de un QFrame container con QVBoxLayout.
# Se eliminan las coordenadas absolutas; la estructura visual es idéntica
# a la versión anterior pero el panel se adapta al container blanco.
#
# Atributos que crea en main_window:
#   mw.Cam1, mw.Cam2, mw.Camgroup
#   mw.BtnBacklight, mw._backlight_style_off, mw._backlight_style_on
# Nota: mw.BtnCall, mw.BtnSet y mw.PresetModeGroup se crean en main_window._build_mode_buttons()

from __future__ import annotations

import threading

import logging
import os
from typing import ClassVar

from PyQt5 import QtCore

from domain.atem_constants import ATEM_INPUT_LABELS as _ATEM_LABELS

logger = logging.getLogger(__name__)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel,
    QPushButton, QSlider, QVBoxLayout, QWidget,
)

from core.events import EventType



class RightPanel:
    """
    Panel derecho de controles PTZ (layout-based).
    Container blanco sobre (1446, 0, 474, 1080). Todos los widgets son hijos
    del container; sus referencias se asignan como atributos de main_window.
    """

    TOGGLE_STYLE = (
        "QPushButton {"
        "  background-color: #DCDCDC; border: none; border-radius: 10px;"
        "  font: 600 18px 'Inter Tight', 'Segoe UI'; color: #777777; padding: 6px 0px;"
        "}"
        "QPushButton:checked {"
        "  background-color: white; color: #111111;"
        "  border: 1px solid #C8C8C8;"
        "}"
    )

    # Default input map: (display label, cam_key). cam_key 0 = no camera on-air.
    # Labels sourced from domain.atem_constants — single source of truth.
    _DEFAULT_ATEM_INPUT_MAP: ClassVar[dict] = {
        1: (_ATEM_LABELS[1], 0),   # PC        — no camera on-air
        2: (_ATEM_LABELS[2], 1),   # Platform  — Cam1 on-air
        3: (_ATEM_LABELS[3], 2),   # Comments  — Cam2 on-air
        4: (_ATEM_LABELS[4], 0),   # None      — no camera on-air
    }

    def __init__(self, main_window):
        self._mw = main_window
        self._joystick_slot = None   # QWidget placeholder para el joystick
        self._atem_has_program = False  # True tras recibir el primer program_changed del ATEM
        self._atem_input_map: dict = dict(self._DEFAULT_ATEM_INPUT_MAP)
        self._build_outer_bg()
        self._build_panel()

    def connect_joystick(self, handlers: dict, stop_handler, speed_provider=None):
        """Inserta el DigitalJoystick en el slot reservado en el layout."""
        from adapters.input.joystick import DigitalJoystick
        mw = self._mw
        slot = self._joystick_slot
        self._joystick = DigitalJoystick(slot, None, None, slot.width(),
                                         handlers, stop_handler, speed_provider)

        # Anillo → slider oculto → VISCA debounce
        self._joystick.zoom_changed.connect(
            lambda pct: mw.ZoomSlider.setValue(int(round(pct))))

        # Slider oculto (actualizado por VISCA feedback) → anillo visual
        mw.ZoomSlider.valueChanged.connect(self._joystick.set_zoom)

        def _zoom_step(current: int) -> int:
            if current < 50:
                return 5
            if current < 60:
                return 4
            if current < 70:
                return 3
            if current < 85:
                return 2
            return 1

        # Botones +/− → slider (la cadena slider→anillo→VISCA ya está cableada)
        self._zoom_plus_btn.clicked.connect(
            lambda: mw.ZoomSlider.setValue(
                min(100, mw.ZoomSlider.value() + _zoom_step(mw.ZoomSlider.value()))))
        self._zoom_minus_btn.clicked.connect(
            lambda: mw.ZoomSlider.setValue(
                max(0, mw.ZoomSlider.value() - _zoom_step(mw.ZoomSlider.value()))))

    def set_joystick_mode(self, mode: str):
        """'platform' → burdeo  |  'comments' → verde."""
        if hasattr(self, '_joystick'):
            self._joystick.set_mode(mode)

    def show_camera_controls(self, visible: bool):
        """Muestra u oculta los controles PTZ/Focus según si la cámara está conectada."""
        self._controls_widget.setVisible(visible)
        self._no_camera_label.setVisible(not visible)
        QtCore.QTimer.singleShot(0, self._fit_container_height)

    # ── Fondo exterior oscuro ─────────────────────────────────────────────────

    def _build_outer_bg(self):
        mw = self._mw
        outer = QFrame(mw)
        outer.setGeometry(1446, 0, 474, 1080)
        outer.setStyleSheet("QFrame { background-color: #B0B0B0; border: none; }")
        outer.lower()

    # ── Container principal con layout ────────────────────────────────────────

    def _build_panel(self):
        mw = self._mw

        # Container blanco — hijo directo de mw, posicionado absolutamente
        self._container = QFrame(mw)
        self._container.setGeometry(1446, 0, 474, 1080)
        self._container.setStyleSheet(
            "QFrame#RightPanelContainer {"
            "  background-color: #F4F4F6;"
            "  border-top-left-radius: 0px;"
            "  border-top-right-radius: 0px;"
            "  border-bottom-left-radius: 8px;"
            "  border-bottom-right-radius: 0px;"
            "  border: none;"
            "}"
        )
        self._container.setObjectName("RightPanelContainer")

        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(14, 16, 14, 16)
        layout.setSpacing(4)

        self._add_camera_selector(layout)

        # ── Contenedor de controles PTZ + Focus/Exposure ──────────────────────
        self._controls_widget = QWidget(self._container)
        ctrl_layout = QVBoxLayout(self._controls_widget)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(4)
        self._add_separator(ctrl_layout)
        self._add_ptz_block(ctrl_layout)
        self._add_separator(ctrl_layout)
        self._add_focus_exposure(ctrl_layout)
        layout.addWidget(self._controls_widget)

        # Widget "Camera not found" — visible solo cuando no hay cámara conectada
        no_cam_container = QWidget(self._container)
        no_cam_layout = QVBoxLayout(no_cam_container)
        no_cam_layout.setContentsMargins(0, 40, 0, 40)
        no_cam_layout.setSpacing(12)
        no_cam_layout.setAlignment(Qt.AlignCenter)
        no_cam_icon = QSvgWidget(os.path.join(self._BASE_DIR, 'no-camera.svg'), no_cam_container)
        no_cam_icon.setFixedSize(64, 64)
        no_cam_text = QLabel('Camera\nnot found', no_cam_container)
        no_cam_text.setAlignment(Qt.AlignCenter)
        no_cam_text.setStyleSheet("QLabel { font: 700 22px 'Inter Tight', 'Segoe UI'; color: #AAAAAA; }")
        no_cam_layout.addWidget(no_cam_icon, 0, Qt.AlignCenter)
        no_cam_layout.addWidget(no_cam_text, 0, Qt.AlignCenter)
        self._no_camera_label = no_cam_container
        self._no_camera_label.hide()
        layout.addWidget(self._no_camera_label)

        layout.addSpacing(6)
        self._add_config_buttons(layout)
        layout.addStretch()

        QtCore.QTimer.singleShot(0, self._fit_container_height)

    def _fit_container_height(self):
        """El panel ocupa siempre toda la altura de la pantalla."""
        self._container.setGeometry(1446, 0, 474, 1080)

    # ── Secciones ─────────────────────────────────────────────────────────────

    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    _ON_AIR_STYLE_STANDBY = (
        "QLabel { font: 700 12px 'Inter Tight', 'Segoe UI'; color: #999999;"
        " background: #EBEBEB; border-radius: 6px; padding: 0px; }"
    )
    _ON_AIR_STYLE_LIVE = (
        "QLabel { font: 700 12px 'Inter Tight', 'Segoe UI'; color: white;"
        " background: #CC2200; border-radius: 6px; padding: 0px; }"
    )

    def _add_camera_selector(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('Camera Selection', self._container))

        cam_row = QFrame(self._container)
        cam_row.setStyleSheet("QFrame { background: transparent; border: none; }")
        row = QHBoxLayout(cam_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        mw.Cam1 = _IndicatorButton('Platform', cam_row)
        mw.Cam1.setCheckable(True)
        mw.Cam1.setAutoExclusive(True)
        mw.Cam1.setChecked(True)
        mw.Cam1.setToolTip('Select Platform Camera')
        mw.Cam1.setStyleSheet(self.TOGGLE_STYLE)
        mw.Cam1.setFixedHeight(62)

        mw.Cam2 = _IndicatorButton('Comments', cam_row)
        mw.Cam2.setCheckable(True)
        mw.Cam2.setAutoExclusive(True)
        mw.Cam2.setToolTip('Select Comments Camera')
        mw.Cam2.setStyleSheet(self.TOGGLE_STYLE)
        mw.Cam2.setFixedHeight(62)

        row.addWidget(mw.Cam1)
        row.addWidget(mw.Cam2)
        layout.addWidget(cam_row)

        # ── ON AIR indicator (oculto hasta que ATEM confirme conexión) ──────
        self._on_air_label = QLabel('● STANDBY', self._container)
        self._on_air_label.setAlignment(Qt.AlignCenter)
        self._on_air_label.setFixedHeight(34)
        self._on_air_label.setStyleSheet(self._ON_AIR_STYLE_STANDBY)
        self._on_air_label.hide()
        layout.addWidget(self._on_air_label)

        # ── PiP indicator (oculto por defecto; visible cuando PiP está activo) ─
        self._pip_label = QLabel('PiP', self._container)
        self._pip_label.setAlignment(Qt.AlignCenter)
        self._pip_label.setFixedHeight(22)
        self._pip_label.setStyleSheet(
            "QLabel { font: 700 11px 'Inter Tight', 'Segoe UI'; color: #FF9800;"
            " background: #3A2800; border-radius: 4px; padding: 0px 6px; }"
        )
        self._pip_label.hide()
        layout.addWidget(self._pip_label)

        mw.Camgroup = QButtonGroup(mw)
        mw.Camgroup.addButton(mw.Cam1)
        mw.Camgroup.addButton(mw.Cam2)
        mw.Cam1.clicked.connect(mw._update_backlight_ui)
        mw.Cam2.clicked.connect(mw._update_backlight_ui)
        mw.Cam1.clicked.connect(mw._update_focus_ui)
        mw.Cam2.clicked.connect(mw._update_focus_ui)
        mw.Cam1.clicked.connect(mw._update_exposure_ui)
        mw.Cam2.clicked.connect(mw._update_exposure_ui)
        mw.Cam1.clicked.connect(lambda: self.set_joystick_mode('platform'))
        mw.Cam2.clicked.connect(lambda: self.set_joystick_mode('comments'))
        mw.Cam1.clicked.connect(mw._update_controls_visibility)
        mw.Cam2.clicked.connect(mw._update_controls_visibility)

    def _add_ptz_block(self, layout: QVBoxLayout):
        """Bloque unificado: Joystick con anillo de zoom + botones +/- a la derecha."""
        mw = self._mw

        block = QFrame(self._container)
        block.setStyleSheet(
            "QFrame { background-color: #F2F2F2; border-radius: 12px; border: none; }"
        )
        bl = QVBoxLayout(block)
        bl.setContentsMargins(0, 8, 0, 8)
        bl.setSpacing(6)

        # ── Slot del joystick (incluirá el anillo de zoom pintado) ───────────
        joy_size = 374
        slot = QWidget(block)
        slot.setFixedSize(joy_size, joy_size)
        self._joystick_slot = slot

        # Slider oculto — conserva toda la lógica VISCA existente
        mw.ZoomSlider = QSlider(Qt.Vertical)
        mw.ZoomSlider.setRange(0, 100)
        mw.ZoomSlider.setValue(0)
        mw.ZoomSlider.hide()

        # ── Columna derecha: botón +, lectura %, botón − ──────────────────────
        right_col = QWidget(block)
        right_col.setFixedWidth(60)
        rc_lay = QVBoxLayout(right_col)
        rc_lay.setContentsMargins(0, 0, 0, 0)
        rc_lay.setSpacing(10)
        rc_lay.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        self._zoom_plus_btn = _CircleButton('+', right_col)
        self._zoom_plus_btn.setFixedSize(38, 38)

        mw.ZoomValueLabel = QLabel('0%', right_col)
        mw.ZoomValueLabel.setAlignment(Qt.AlignCenter)
        mw.ZoomValueLabel.setStyleSheet(
            "font: 600 12px 'IBM Plex Mono', 'Consolas'; color: #666666;")

        zoom_lbl = QLabel('ZOOM', right_col)
        zoom_lbl.setAlignment(Qt.AlignCenter)
        zoom_lbl.setStyleSheet(
            "font: 700 8px 'Inter Tight', 'Segoe UI'; color: #AAAAAA; letter-spacing: 1px;")

        self._zoom_minus_btn = _CircleButton('−', right_col)
        self._zoom_minus_btn.setFixedSize(38, 38)

        rc_lay.addStretch()
        rc_lay.addWidget(self._zoom_plus_btn, alignment=Qt.AlignHCenter)
        rc_lay.addWidget(mw.ZoomValueLabel)
        rc_lay.addWidget(zoom_lbl)
        rc_lay.addWidget(self._zoom_minus_btn, alignment=Qt.AlignHCenter)
        rc_lay.addStretch()

        joy_right_row = QHBoxLayout()
        joy_right_row.setSpacing(0)
        joy_right_row.addWidget(slot, alignment=Qt.AlignTop)
        joy_right_row.addSpacing(12)
        joy_right_row.addWidget(right_col, alignment=Qt.AlignVCenter)
        bl.addLayout(joy_right_row)

        # ── HOME manual (solo visible si ATEM no detectado) ──────────────
        self._home_btn = QPushButton('Comments → Home', block)
        self._home_btn.setFixedHeight(44)
        self._home_btn.setContentsMargins(0, 0, 0, 0)
        self._home_btn.setStyleSheet(
            "QPushButton {"
            "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "    stop:0 #E8A020, stop:1 #B06010);"
            "  border: none; border-radius: 10px;"
            "  font: 700 14px 'Inter Tight', 'Segoe UI'; color: white;"
            "}"
            "QPushButton:pressed { background: #805010; }"
        )
        self._home_btn.clicked.connect(lambda: mw._bus.emit(EventType.CAMERA_HOME, camera=2))
        self._home_btn.hide()
        bl.addSpacing(6)
        bl.addWidget(self._home_btn)

        # Debounce: slider oculto → CameraPort zoom_absolute
        mw._zoom_timer = QtCore.QTimer(block)
        mw._zoom_timer.setSingleShot(True)
        mw._zoom_timer.setInterval(150)

        def _send_zoom_absolute():
            port = getattr(mw, '_camera_port', None)
            if port is None:
                return
            cam_id = "cam1" if mw.Cam1.isChecked() else "cam2"
            port.zoom_absolute(cam_id, mw.ZoomSlider.value())

        mw._zoom_timer.timeout.connect(_send_zoom_absolute)
        mw._zoom_feedback = False
        mw.ZoomSlider.valueChanged.connect(
            lambda v: (mw.ZoomValueLabel.setText(f"{v}%"),
                       None if mw._zoom_feedback else mw._zoom_timer.start()))

        mw.Cam1.clicked.connect(mw._refresh_zoom)
        mw.Cam2.clicked.connect(mw._refresh_zoom)

        # ── Display de estado de cámara simulada (solo en modo sim) ──────────
        import adapters.sim_mode as _sm
        if _sm.is_active():
            from simulation.debug_panel import attach_sim_debug_panel
            attach_sim_debug_panel(bl, mw)

        layout.addWidget(block)

    def _add_separator(self, layout: QVBoxLayout):
        layout.addSpacing(14)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(line)
        layout.addSpacing(14)

    def _add_focus_exposure(self, layout: QVBoxLayout):
        mw = self._mw
        layout.addWidget(_section_label('Focus & Exposure', self._container))

        self._btn_focus_base_style = (
            "QPushButton {"
            "  background-color: #DCDCDC; border: none; border-radius: 10px;"
            "  font: 600 13px 'Inter Tight', 'Segoe UI'; color: #555555; padding: 4px 0px;"
            "}"
            "QPushButton:pressed { background-color: #B8B8B8; color: #111111; }"
        )

        def _active_cam_id() -> str:
            return "cam1" if mw.Cam1.isChecked() else "cam2"

        def _run_off_ui(fn, *args):
            """Comando confirmado FUERA del hilo UI (daemon thread).

            focus/exposure/backlight son comandos confirmados: esperan la
            respuesta VISCA y pueden bloquear segundos si la cámara no
            responde. En el hilo Qt congelarían la app y, lo peor, impedirían
            pulsar STOP durante la espera. Sin resultado visual dependiente:
            el feedback de foco llega por el polling de estado.
            """
            threading.Thread(
                target=fn, args=args, daemon=True, name="CameraCmdOffUI",
            ).start()

        def _get_port():
            return getattr(mw, '_camera_port', None)

        # Fila superior: foco
        focus_row = QHBoxLayout()
        focus_row.setSpacing(5)
        self.btn_auto_focus   = QPushButton('Auto\nFocus',   self._container)
        self.btn_one_push_af  = QPushButton('One Push\nAF',  self._container)
        self.btn_manual_focus = QPushButton('Manual\nFocus', self._container)
        for btn, tooltip, port_method in [
            (self.btn_auto_focus,   'Auto Focus ON',                   'focus_auto'),
            (self.btn_one_push_af,  'One-shot autofocus, then manual', 'one_push_af'),
            (self.btn_manual_focus, 'Manual Focus mode',               'focus_manual'),
        ]:
            btn.setFixedHeight(50)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(self._btn_focus_base_style)
            btn.clicked.connect(
                (lambda m=port_method: (
                    lambda: _run_off_ui(getattr(_get_port(), m, lambda _: None), _active_cam_id())
                ))()
            )
            focus_row.addWidget(btn)
        layout.addLayout(focus_row)

        # Fila inferior: exposición + backlight
        exp_row = QHBoxLayout()
        exp_row.setSpacing(5)
        self.btn_darker   = QPushButton('▼ Darker\n0',   self._container)
        self.btn_brighter = QPushButton('▲ Brighter\n0', self._container)
        for btn, tooltip, port_method in [
            (self.btn_darker,   'Decrease exposure one step', 'brightness_down'),
            (self.btn_brighter, 'Increase exposure one step', 'brightness_up'),
        ]:
            btn.setFixedHeight(50)
            btn.setToolTip(tooltip)
            btn.setStyleSheet(self._btn_focus_base_style)
            btn.clicked.connect(
                (lambda m=port_method: (
                    lambda: _run_off_ui(getattr(_get_port(), m, lambda _: None), _active_cam_id())
                ))()
            )
            exp_row.addWidget(btn)

        mw.BtnBacklight = QPushButton('Backlight\nOFF', self._container)
        mw.BtnBacklight.setFixedHeight(50)
        mw.BtnBacklight.setToolTip('Toggle backlight compensation')
        mw._backlight_style_off = (
            "QPushButton { background-color: #DCDCDC; border: none; border-radius: 10px;"
            " font: 600 13px 'Inter Tight', 'Segoe UI'; color: #555555; padding: 4px 0px; }"
        )
        mw._backlight_style_on = (
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,"
            " stop:0 #F5B820, stop:1 #B87800);"
            " border: none; border-radius: 10px;"
            " font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; padding: 4px 0px; }"
        )
        mw.BtnBacklight.setStyleSheet(mw._backlight_style_off)

        def _on_backlight_clicked():
            port = _get_port()
            if port:
                _run_off_ui(port.backlight_toggle, _active_cam_id())

        mw.BtnBacklight.clicked.connect(_on_backlight_clicked)

        # Insertar backlight en posición central
        exp_row.insertWidget(1, mw.BtnBacklight)
        layout.addLayout(exp_row)

    # ── Helpers de feedback visual ─────────────────────────────────────────────

    def set_focus_mode(self, mode: str):
        """Destaca el botón de foco activo (auto/manual). One Push AF nunca persiste."""
        _ACTIVE = (
            "QPushButton { background-color: #2979D9; border: none; border-radius: 10px;"
            " font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; padding: 4px 0px; }"
        )
        self.btn_auto_focus.setStyleSheet(
            _ACTIVE if mode == 'auto' else self._btn_focus_base_style)
        self.btn_manual_focus.setStyleSheet(
            _ACTIVE if mode == 'manual' else self._btn_focus_base_style)
        self.btn_one_push_af.setStyleSheet(self._btn_focus_base_style)

    def set_exposure_level(self, level: int):
        """Actualiza el texto de los botones Darker/Brighter con el nivel numérico."""
        sign = '+' if level > 0 else ''
        self.btn_darker.setText(f'▼ Darker\n{sign}{level}')
        self.btn_brighter.setText(f'▲ Brighter\n{sign}{level}')

    def _flash_button(self, btn: QPushButton, success: bool, duration_ms: int = 1400):
        """Flash verde (éxito) o rojo (fallo) en el botón, luego restaura el estilo base."""
        color = '#3d9e3d' if success else '#b33030'
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color}; border: none; border-radius: 10px;"
            f" font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; padding: 4px 0px; }}"
        )
        QtCore.QTimer.singleShot(
            duration_ms, lambda: btn.setStyleSheet(self._btn_focus_base_style))


    def set_atem_state(self, state) -> None:
        """Muestra ON AIR solo cuando ATEM está CONNECTED y ya se ha recibido
        al menos un evento program_changed (operativo al 100%).  En cualquier
        otro caso muestra el botón amarillo Comments → Home."""
        from domain.atem_state import ATEMState
        connected = (state == ATEMState.CONNECTED)
        if not connected:
            self._atem_has_program = False
            self._mw.Cam1.set_on_air(False)
            self._mw.Cam2.set_on_air(False)
            self._pip_label.hide()
        operative = connected and self._atem_has_program
        self._on_air_label.setVisible(operative)
        self._home_btn.setVisible(not operative)
        QtCore.QTimer.singleShot(0, self._fit_container_height)

    def set_atem_input_names(self, names: dict) -> None:
        """Actualiza los labels de los inputs con los nombres reales del ATEM.

        Resetea al mapa base antes de aplicar para evitar entradas obsoletas de
        conexiones anteriores. Solo reemplaza la etiqueta de texto; el cam_key
        (qué cámara se marca en antena) se mantiene de _DEFAULT_ATEM_INPUT_MAP.
        """
        self._atem_input_map = dict(self._DEFAULT_ATEM_INPUT_MAP)
        for input_id, name in names.items():
            cam_key = self._atem_input_map.get(input_id, (f"Input {input_id}", 0))[1]
            self._atem_input_map[input_id] = (name, cam_key)
        logger.debug("[ATEM] Input map actualizado con nombres del switcher: %s",
                     self._atem_input_map)

    def set_atem_program(self, input_num: int):
        """Actualiza el indicador ON AIR según el input de programa del ATEM."""
        entry = self._atem_input_map.get(input_num)
        if entry is not None:
            label, on_air_cam = entry
            text  = f'● ON AIR — {label}'
            style = self._ON_AIR_STYLE_LIVE
        else:
            text       = '● STANDBY'
            style      = self._ON_AIR_STYLE_STANDBY
            on_air_cam = 0
        self._on_air_label.setText(text)
        self._on_air_label.setStyleSheet(style)
        # Primer programa recibido: pasar de botón amarillo a label ON AIR
        if not self._atem_has_program:
            self._atem_has_program = True
            self._on_air_label.setVisible(True)
            self._home_btn.setVisible(False)
            QtCore.QTimer.singleShot(0, self._fit_container_height)
        # Indicar en los botones de cámara cuál está en antena
        self._mw.Cam1.set_on_air(on_air_cam == 1)
        self._mw.Cam2.set_on_air(on_air_cam == 2)

    def set_pip_state(self, pip_state) -> None:
        """Muestra/oculta el indicador PiP y su fuente cuando PiP está activo."""
        if pip_state is None or not pip_state.enabled:
            self._pip_label.hide()
            return
        src = pip_state.source
        label_text = "PiP ON" if src is None else f"PiP ON — src {src}"
        self._pip_label.setText(label_text)
        self._pip_label.show()
        QtCore.QTimer.singleShot(0, self._fit_container_height)

    def _add_config_buttons(self, layout: QVBoxLayout):
        mw = self._mw

        sep = QFrame(self._container)
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #E0E0E0;")
        layout.addWidget(sep)
        layout.addSpacing(10)

        gear_row = QHBoxLayout()
        gear_row.setSpacing(8)

        # ── Botón ⚙ Settings — visible cuando el rol tiene acceso a configuración
        btn_gear = QPushButton('⚙  Settings', self._container)
        btn_gear.setFixedHeight(36)
        btn_gear.setToolTip('Camera and system configuration (Technician / Admin)')
        btn_gear.setStyleSheet(
            "QPushButton { background: rgba(80,80,80,50); border: 1px solid #B8B8B8;"
            " border-radius: 8px; font: 600 13px 'Inter Tight', 'Segoe UI'; color: #444; padding: 0 14px; }"
            "QPushButton:pressed { background: rgba(80,80,80,120); }"
        )
        btn_gear.clicked.connect(mw._open_config_dialog)
        gear_row.addWidget(btn_gear, stretch=1)
        self._btn_gear = btn_gear

        # ── Botón ← Operador — sale del modo técnico inline (sin contraseña)
        btn_exit_admin = QPushButton('← Operator', self._container)
        btn_exit_admin.setFixedHeight(36)
        btn_exit_admin.setToolTip('Switch back to Operator mode')
        btn_exit_admin.setStyleSheet(
            "QPushButton { background: rgba(80,80,80,30); border: 1px solid #C8C8C8;"
            " border-radius: 8px; font: 600 13px 'Inter Tight', 'Segoe UI'; color: #666; padding: 0 14px; }"
            "QPushButton:hover { background: rgba(80,80,80,70); }"
            "QPushButton:pressed { background: rgba(80,80,80,120); }"
        )
        btn_exit_admin.clicked.connect(mw._exit_admin_mode)
        gear_row.addWidget(btn_exit_admin, stretch=1)
        self._btn_exit_admin = btn_exit_admin

        # ── Botón 🔑 Admin Mode — sube a Técnico inline con contraseña (no reinicia)
        btn_enter_admin = QPushButton('Admin Mode', self._container)
        btn_enter_admin.setFixedHeight(36)
        btn_enter_admin.setToolTip('Enter Technician mode with password (no restart required)')
        btn_enter_admin.setStyleSheet(
            "QPushButton { background: rgba(46,82,41,0.08); border: 1px solid rgba(46,82,41,0.30);"
            " border-radius: 8px; font: 600 13px 'Inter Tight', 'Segoe UI';"
            " color: #2E5229; padding: 0 14px; }"
            "QPushButton:hover { background: rgba(46,82,41,0.15); border-color: rgba(46,82,41,0.50); }"
            "QPushButton:pressed { background: rgba(46,82,41,0.25); }"
        )
        btn_enter_admin.clicked.connect(mw._enter_admin_mode_inline)
        gear_row.addWidget(btn_enter_admin, stretch=1)
        self._btn_enter_admin = btn_enter_admin

        self._gear_sep = sep
        layout.addLayout(gear_row)
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        """Actualiza visibilidad de los botones de rol según el modo activo.

        Operador (CAMERA_OPERATOR / BASIC_OPERATOR):
            [ 🔑 Admin Mode ]

        Técnico / Admin (TECHNICIAN / SYSTEM_ADMIN):
            [ ⚙ Settings ]  [ ← Operador ]
        """
        from domain.call_set_policy import OperatingMode
        _SETTINGS_ROLES = {OperatingMode.TECHNICIAN, OperatingMode.SYSTEM_ADMIN,
                           OperatingMode.ADMIN_INSTALLER}
        has_settings = self._mw._access_mode_svc.mode in _SETTINGS_ROLES
        self._btn_gear.setVisible(has_settings)
        self._btn_exit_admin.setVisible(has_settings)
        self._btn_enter_admin.setVisible(not has_settings)


# ── Widgets personalizados ────────────────────────────────────────────────────

class _IndicatorButton(QPushButton):
    """QPushButton con dos indicadores pintados:
      - Esquina superior derecha: punto rojo cuando está seleccionado (checked).
      - Esquina superior izquierda: LED verde/ámbar/rojo de estado.
        Verde = cámara encendida (sesión activa) y conectada en red.
        Ámbar = reconexión en curso: la app está recuperando la cámara.
        Rojo  = cámara apagada (sesión inactiva) o sin conexión de red.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._connected: bool = False
        self._powered: bool = False
        self._on_air: bool = False
        self._connecting: bool = False

    def set_connected(self, connected: bool):
        if connected != self._connected:
            self._connected = connected
            self.update()

    def set_connecting(self, connecting: bool):
        """Ámbar en el LED mientras el worker intenta (re)conectar la cámara."""
        if connecting != self._connecting:
            self._connecting = connecting
            self.update()

    def set_powered(self, powered: bool):
        if powered != self._powered:
            self._powered = powered
            self.update()

    def set_on_air(self, on_air: bool):
        if on_air != self._on_air:
            self._on_air = on_air
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = 5
        margin = 8

        # LED de estado (esquina superior izquierda): verde=activa, rojo=apagada
        lx = margin
        ly = margin
        if self._powered and self._connected:
            outer_halo = QColor(35, 170, 70, 46)
            inner_halo = QColor(35, 170, 70, 102)
            core_color = QColor(95, 217, 127, 230)
        elif self._connecting and not self._connected:
            # Ámbar: (re)conexión en curso — el operador ve que la app está
            # recuperando la cámara sin tocar nada.
            outer_halo = QColor(210, 150, 20, 46)
            inner_halo = QColor(210, 150, 20, 115)
            core_color = QColor(240, 190, 60, 230)
        else:
            outer_halo = QColor(190, 35, 35, 46)
            inner_halo = QColor(190, 35, 35, 115)
            core_color = QColor(224, 80, 80, 230)
        painter.setPen(Qt.NoPen)
        painter.setBrush(outer_halo)
        painter.drawEllipse(lx - 5, ly - 5, r * 2 + 10, r * 2 + 10)
        painter.setBrush(inner_halo)
        painter.drawEllipse(lx - 2, ly - 2, r * 2 + 4, r * 2 + 4)
        painter.setBrush(core_color)
        painter.drawEllipse(lx, ly, r * 2, r * 2)

        # Etiqueta ON AIR (esquina superior derecha): rojo vivo cuando esta camara esta en antena
        if self._on_air:
            from PyQt5.QtCore import QRect as _QRect
            from PyQt5.QtGui import QFont as _QFont
            tag_w, tag_h = 52, 16
            tag_x = self.width() - tag_w - margin + 2
            tag_y = margin - 2
            painter.setBrush(QColor(210, 30, 10))
            painter.drawRoundedRect(tag_x, tag_y, tag_w, tag_h, 4, 4)
            painter.setFont(_QFont('Inter Tight', 7, _QFont.Bold))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(_QRect(tag_x, tag_y, tag_w, tag_h), Qt.AlignCenter, 'ON AIR')

        painter.end()


class _CircleButton(QLabel):
    """Botón circular con símbolo centrado garantizado vía paintEvent manual."""

    clicked = pyqtSignal()

    _S_NORMAL  = "QLabel { background:#FFFFFF; border:1.5px solid #E0E0E0; border-radius:19px; }"
    _S_HOVER   = "QLabel { background:#F2F2F2; border:1.5px solid #BBBBBB; border-radius:19px; }"
    _S_PRESSED = "QLabel { background:#E0E0E0; border:1.5px solid #BBBBBB; border-radius:19px; }"
    _FONT      = QFont('Inter Tight', 20, QFont.Bold)

    def __init__(self, symbol: str, parent=None):
        super().__init__('', parent)        # texto vacío: QLabel no dibuja nada
        self._symbol = symbol
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._S_NORMAL)

    def paintEvent(self, event):
        super().paintEvent(event)           # fondo + borde del stylesheet
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(self._FONT)
        p.setPen(QColor('#444444'))
        p.drawText(self.rect(), Qt.AlignCenter, self._symbol)
        p.end()

    def enterEvent(self, _):
        self.setStyleSheet(self._S_HOVER)

    def leaveEvent(self, _):
        self.setStyleSheet(self._S_NORMAL)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setStyleSheet(self._S_PRESSED)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setStyleSheet(self._S_NORMAL)
            if self.rect().contains(event.pos()):
                self.clicked.emit()


# ── Helpers de módulo ─────────────────────────────────────────────────────────

def _section_label(text: str, parent: QWidget) -> QLabel:
    lbl = QLabel(text, parent)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setStyleSheet("font: 600 15px 'Inter Tight', 'Segoe UI'; color: #555555; padding-bottom: 10px;")
    return lbl
