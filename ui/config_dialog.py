#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# config_dialog.py — Diálogo modal de configuración técnica
#
# Responsabilidad única: mostrar en un diálogo modal todos los controles
# técnicos que antes estaban siempre visibles en el panel derecho:
#   - IP y VISCA ID de cámara Platform
#   - IP y VISCA ID de cámara Comments
#   - Label de versión
#   - Botón de ayuda (contacto soporte)
#
# MOTIVO DE EXTRACCIÓN:
#   Estos controles los usa el técnico/administrador, no el operador de cámara.
#   Esconderlos bajo un engranaje ⚙ reduce el ruido visual del panel derecho
#   y evita cambios accidentales de IP durante una sesión en directo.
#
# DISEÑO DEL DIÁLOGO:
#   - QDialog modal (bloquea la ventana principal mientras está abierto)
#   - No tiene botón OK/Cancel: cada acción (cambiar IP, cambiar ID) se
#     ejecuta directamente con su botón propio, igual que antes.
#   - Se cierra con el botón "Close" del diálogo o con Escape.
#   - Los colores de los labels de IP/ID reflejan el estado de conectividad
#     (CAM1.check / CAM2.check): verde = responde, rojo = no responde.
#
# USO EN main_window.py:
#   from ui.config_dialog import ConfigDialog
#   dlg = ConfigDialog(self)
#   dlg.exec_()   # modal — bloquea hasta que se cierre

# PEP 604 unions (`X | None`) en anotaciones requieren Python 3.10+ si se
# evalúan en runtime. En Raspberry Pi OS Bullseye (Python 3.9.2) eso provoca
# `TypeError: unsupported operand type(s) for |`. Con anotaciones diferidas se
# almacenan como cadenas y no se evalúan al importar. Mantener como primer import.
from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path
import threading
from typing import Optional

from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QScrollArea, QWidget, QTabWidget,
    QGraphicsOpacityEffect,
)

from app_version import APP_NAME
from ui.config_pages.test_tab import build_test_tab
from ui.config_pages.session_tab import build_session_tab
from ui.config_pages.data_tab import build_data_tab
from ui.config_pages.access_tab import build_access_tab
from ui.config_pages.cameras_tab import build_cameras_tab
from ui.config_pages.atem_tab import build_atem_tab
from ui.config_pages.sections import (
    build_preset_validation_section,
    build_status_strip,
)
from ui import styles as _S
from ui.styles import (
    apply_shadow as _apply_shadow,
    close_button_qss,
    svg_icon as _svg_icon,
    svg_icon_from_markup as _svg_icon_markup,
)
import adapters.sim_mode as _sim_mode


# Los sub-diálogos de edición y el helper de ruta viven en
# ui.config_edit_dialogs; se re-exportan para `from ui.config_dialog import ...`.
from ui.config_edit_dialogs import (  # noqa: F401  (re-exported for callers/tests)
    _CamEditDialog,
    _ATEMEditDialog,
    _config_yaml_path,
)

# ── Design tokens (single source of truth in ui/styles.py) ─────────────────────
_C_BRAND_DARK  = _S.BRAND_DARK
_C_BRAND_MID   = _S.BRAND_MID
_C_BRAND_LIGHT = _S.BRAND_LIGHT
_C_SUCCESS     = _S.SUCCESS
_C_SUCCESS_BG  = _S.SUCCESS_BG
_C_SUCCESS_BD  = _S.SUCCESS_BD
_C_WARNING     = _S.WARNING
_C_WARNING_BG  = _S.WARNING_BG
_C_WARNING_BD  = _S.WARNING_BD
_C_ERROR       = _S.ERROR
_C_ERROR_BG    = _S.ERROR_BG
_C_ERROR_BD    = _S.ERROR_BD
_C_CARD_BD     = _S.CARD_BD
_C_FIELD_BG    = _S.FIELD_BG
_C_FIELD_BD    = _S.FIELD_BD
_C_MUTED       = _S.MUTED
_C_SECONDARY   = _S.SECONDARY


# ── Button line-icons (paths copied verbatim from the v3 design) ──────────────
# Authored monochrome (stroke/fill #000) and tinted per-button at render time.
def _svg(inner: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">{inner}</svg>'


_ICON_SVGS = {
    'stop':     _svg('<rect x="3.5" y="3.5" width="9" height="9" rx="1.4" stroke="#000" stroke-width="1.6" fill="none"/>'),
    'minus':    _svg('<path d="M3 8h10" stroke="#000" stroke-width="1.8" stroke-linecap="round"/>'),
    'plus':     _svg('<path d="M8 3v10M3 8h10" stroke="#000" stroke-width="1.6" stroke-linecap="round"/>'),
    'refresh':  _svg('<path d="M3 8a5 5 0 119 3.5M12 12v-3.5h-3.5" stroke="#000" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    'sync':     _svg('<path d="M3 8a5 5 0 019-3l1 1m0-3v3h-3M13 8a5 5 0 01-9 3l-1-1m0 3v-3h3" stroke="#000" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    'search':   _svg('<circle cx="7" cy="7" r="4.5" stroke="#000" stroke-width="1.6" fill="none"/><path d="M10.5 10.5L14 14" stroke="#000" stroke-width="1.6" stroke-linecap="round"/>'),
    'monitor':  _svg('<rect x="2.5" y="4" width="11" height="8" rx="1.4" stroke="#000" stroke-width="1.5" fill="none"/><path d="M5 14h6" stroke="#000" stroke-width="1.5" stroke-linecap="round"/>'),
    'bolt':     _svg('<path d="M9 2L4 9h3l-1 5 5-7H8l1-5z" fill="#000"/>'),
    'play':     _svg('<path d="M5 3.5l7 4.5-7 4.5V3.5z" fill="#000"/>'),
    'square':   _svg('<rect x="4" y="4" width="8" height="8" rx="1.2" fill="#000"/>'),
    'lock':     _svg('<rect x="3" y="7" width="10" height="7" rx="1.2" stroke="#000" stroke-width="1.6" fill="none"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2" stroke="#000" stroke-width="1.6" fill="none" stroke-linecap="round"/>'),
    'calendar': _svg('<rect x="2.5" y="3.5" width="11" height="10" rx="1.2" stroke="#000" stroke-width="1.6" fill="none"/><path d="M2.5 6.5h11M5.5 2v3M10.5 2v3" stroke="#000" stroke-width="1.6" stroke-linecap="round"/>'),
    'export':   _svg('<path d="M8 2v8m0 0l3-3m-3 3L5 7M3 12.5h10" stroke="#000" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    'import':   _svg('<path d="M8 11V3m0 8L5 8m3 3l3-3M3 13.5h10" stroke="#000" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
    'help':     _svg('<circle cx="8" cy="8" r="6" stroke="#000" stroke-width="1.6" fill="none"/><path d="M6.5 6a1.5 1.5 0 113 0c0 .8-.6 1.2-1.2 1.6-.4.3-.8.6-.8 1.1M8 11.2h.01" stroke="#000" stroke-width="1.6" fill="none" stroke-linecap="round"/>'),
    'logout':   _svg('<path d="M7 3h-3a1 1 0 00-1 1v8a1 1 0 001 1h3M10 5l3 3-3 3M13 8H6" stroke="#000" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'),
}

# Per-variant icon tint — white reads on filled buttons, slate on ghost/outlined.
_ICON_TINT = {
    'primary': 'white', 'danger': 'white', 'info': 'white',
    'ghost': _C_SECONDARY,
}

# Standard button width. Every stand-alone action button is exactly this wide so
# the dialog reads as a consistent set rather than a mix of full-width and
# text-hugging buttons. Buttons that live in a multi-button row instead share the
# row width equally (width='row').
_BTN_STD = 210

# ── LED indicators ────────────────────────────────────────────────────────────
# Faking a circle with QFrame + QSS border-radius proved unreliable (the dots
# collapsed to slivers). Instead each LED is an antialiased circular PIXMAP
# painted with QPainter and shown on a QLabel — the same reliable path the SVG
# icons use. Glossy: an off-centre radial highlight over a darker base + ring.
_LED_SIZE = 14

# state -> (highlight, base, ring)
_LED_COLORS = {
    'green': ('#7BE89A', '#1E9F40', '#147A2C'),
    'red':   ('#F47A7A', '#C62020', '#8E1414'),
    'amber': ('#F9C45F', '#D4860A', '#9A6207'),
    'off':   ('#D2D6D2', '#9CA29C', '#787E78'),
}


def _led_pixmap(state: str, size: int = _LED_SIZE):
    """Paint a glossy round LED to a QPixmap (2x for crisp edges)."""
    from PyQt5.QtCore import Qt as _Qt
    from PyQt5.QtGui import QPixmap, QPainter, QRadialGradient, QColor, QPen
    light, base, ring = _LED_COLORS.get(state, _LED_COLORS['off'])
    scale = 2
    s = size * scale
    pm = QPixmap(s, s)
    pm.fill(_Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QRadialGradient(s * 0.36, s * 0.30, s * 0.85)
    grad.setColorAt(0.0, QColor(light))
    grad.setColorAt(1.0, QColor(base))
    p.setBrush(grad)
    p.setPen(QPen(QColor(ring), scale))
    m = scale  # inset so the ring isn't clipped
    p.drawEllipse(m, m, s - 2 * m, s - 2 * m)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def _make_pencil_icon(size=18):
    """Renderiza edit.svg a un QIcon del tamaño dado."""
    svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'edit.svg')
    return _svg_icon(svg_path, size), size


class ConfigDialog(QDialog):
    """
    Diálogo modal de configuración técnica de cámaras.

    Recibe la MainWindow como parent para heredar posición y acceder
    a sus métodos (_session, _dialogs, _cameras).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Camera Configuration')
        self.setWindowModality(Qt.WindowModal)
        self.setFixedSize(780, 760)
        # Sin barra de título del SO en pantalla táctil (RPi fullscreen)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)

        self.setStyleSheet(
            "ConfigDialog {"
            "  background: white;"
            f"  border: 1px solid {_C_CARD_BD};"
            "  border-radius: 14px;"
            "}"
        )

        _apply_shadow(self, blur=48, offset=(0, 12))

        self._build_ui(parent)

    def _build_ui(self, mw):
        """
        Construye el contenido del diálogo.
        mw — referencia a MainWindow para conectar los callbacks existentes.
        """
        # Calculado una vez aquí y reutilizado en todas las secciones
        sim_active = _sim_mode.is_active()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Header (dlg-head) ────────────────────────────────────────────
        head_widget = QWidget()
        head_widget.setStyleSheet(
            f"background: white; border-bottom: 1px solid {_C_CARD_BD};"
            " border-top-left-radius: 14px; border-top-right-radius: 14px;"
        )
        head_h = QHBoxLayout(head_widget)
        head_h.setContentsMargins(18, 14, 14, 14)
        head_h.setSpacing(12)

        # Icon square
        icon_sq = QLabel()
        icon_sq.setFixedSize(36, 36)
        icon_sq.setAlignment(Qt.AlignCenter)
        icon_sq.setText('⬛')
        icon_sq.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f" stop:0 {_C_BRAND_MID}, stop:1 {_C_BRAND_DARK});"
            " border-radius: 10px; color: white; font: bold 18px;"
        )

        # Camera SVG icon inside, tinted white to read on the green gradient
        # (design §header: white camera glyph in a 38px brand-gradient square).
        _cam_svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'camera.svg')
        icon_sq.setPixmap(_svg_icon(_cam_svg_path, 20, color='white').pixmap(20, 20))

        head_h.addWidget(icon_sq)

        # Title + subtitle
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title_lbl = QLabel('Camera Configuration')
        title_lbl.setStyleSheet(
            f"font: 700 18px 'Inter Tight', 'Segoe UI'; color: {_C_BRAND_DARK};"
            " background: transparent;"
        )
        subtitle_lbl = QLabel(f'PTZ & runtime profile · {APP_NAME}')
        subtitle_lbl.setStyleSheet(
            f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
            " background: transparent;")
        title_col.addWidget(title_lbl)
        title_col.addWidget(subtitle_lbl)
        head_h.addLayout(title_col)
        head_h.addStretch()

        # Outlined close button
        btn_x = QPushButton('✕')
        btn_x.setFixedSize(36, 36)
        btn_x.setStyleSheet(close_button_qss(radius=8, font_px=15))
        btn_x.clicked.connect(self.accept)
        head_h.addWidget(btn_x)
        root_layout.addWidget(head_widget)

        # ── Global status strip (B) ──────────────────────────────────────
        self._status_strip_widget = build_status_strip(self, mw)
        root_layout.addWidget(self._status_strip_widget)

        # ── Tabs ─────────────────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setStyleSheet(
            "QTabWidget::pane {"
            f"  border: none; background: #FAFAF9;"
            "}"
            "QTabBar {"
            "  background: white;"
            f"  border-bottom: 1px solid {_C_CARD_BD};"
            "}"
            "QTabBar::tab {"
            "  background: white; color: #7A807A;"
            "  padding: 11px 18px 9px;"
            "  margin: 0 1px;"
            "  border: none;"
            "  border-bottom: 3px solid transparent;"
            "  min-width: 84px; min-height: 34px;"
            "  font: 600 13px 'Inter Tight', 'Segoe UI';"
            "}"
            "QTabBar::tab:selected {"
            f"  color: {_C_BRAND_DARK};"
            f"  background: {_S.SUCCESS_BG};"
            f"  border-bottom: 3px solid {_C_BRAND_MID};"
            "  font: 700 13px 'Inter Tight', 'Segoe UI';"
            "}"
            "QTabBar::tab:hover:!selected {"
            "  background: #F2F5F1; color: #2E5229;"
            "  border-bottom: 3px solid #C8D6C4;"
            "}"
        )

        def _make_tab(name: str):
            tab = QWidget()
            tab.setStyleSheet("background: #FAFAF9;")
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(14, 14, 14, 14)
            tab_layout.setSpacing(12)
            tabs.addTab(tab, name)
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setFrameShape(QFrame.NoFrame)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setStyleSheet(
                "QScrollArea { background: transparent; border: none; }"
                "QScrollBar:vertical {"
                "  background: transparent;"
                "  width: 6px;"
                "  margin: 4px 2px 4px 0px;"
                "}"
                "QScrollBar::handle:vertical {"
                f" background: {_C_FIELD_BD};"
                "  min-height: 32px;"
                "  border-radius: 3px;"
                "}"
                "QScrollBar::handle:vertical:hover {"
                f" background: {_C_MUTED};"
                "}"
                "QScrollBar::handle:vertical:pressed {"
                f" background: {_C_BRAND_LIGHT};"
                "}"
                "QScrollBar::add-line:vertical,"
                "QScrollBar::sub-line:vertical {"
                "  height: 0px;"
                "}"
                "QScrollBar::add-page:vertical,"
                "QScrollBar::sub-page:vertical {"
                "  background: none;"
                "}"
            )
            content = QWidget()
            content.setStyleSheet("background: transparent;")
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 8, 0)
            content_layout.setSpacing(12)
            scroll_area.setWidget(content)
            tab_layout.addWidget(scroll_area)
            return content_layout

        # _card helper: builds a styled card frame, appends it to parent_layout,
        # and returns the body layout for adding children.
        def _panel_layout(parent_layout, title_text: str, badge_text: Optional[str] = None,
                          badge_kind: str = 'muted', accent: Optional[str] = None):
            """Crea un card visual para agrupar controles relacionados."""
            card = QFrame()
            card.setObjectName("ConfigCard")
            card.setStyleSheet(
                "QFrame#ConfigCard {"
                f"  border: 1px solid {_C_CARD_BD};"
                "  border-radius: 12px;"
                "  background: #FCFCFB;"
                "}"
            )
            card_v = QVBoxLayout(card)
            card_v.setContentsMargins(0, 0, 0, 0)
            card_v.setSpacing(0)

            # Card header row
            card_head = QWidget()
            card_head.setStyleSheet(
                f"background: white; border-bottom: 1px solid {_C_CARD_BD};"
                " border-top-left-radius: 12px; border-top-right-radius: 12px;"
            )
            head_row = QHBoxLayout(card_head)
            head_row.setContentsMargins(16, 12, 16, 12)
            head_row.setSpacing(8)

            head_title = QLabel(title_text.upper())
            head_title.setStyleSheet(
                "font: 700 11px 'Inter Tight', 'Segoe UI', sans-serif;"
                f" color: {_C_MUTED}; letter-spacing: 0.10em;"
                " background: transparent;"
            )
            head_row.addWidget(head_title, stretch=1)

            if badge_text:
                badge_lbl = self._badge(badge_text, badge_kind)
                head_row.addWidget(badge_lbl)

            card_v.addWidget(card_head)

            # Card body
            body_w = QWidget()
            body_w.setStyleSheet("background: transparent;")
            body_layout = QVBoxLayout(body_w)
            body_layout.setContentsMargins(14, 11, 14, 12)
            body_layout.setSpacing(9)
            card_v.addWidget(body_w)

            if accent:
                # Left accent stripe
                card.setStyleSheet(
                    "QFrame#ConfigCard {"
                    f"  border: 1px solid {_C_CARD_BD};"
                    "  border-radius: 12px;"
                    "  background: #FCFCFB;"
                    f"  border-left: 3px solid {accent};"
                    "}"
                )

            parent_layout.addWidget(card)
            return body_layout

        session_layout = _make_tab('Session')
        cameras_layout = _make_tab('Cameras')
        atem_layout    = _make_tab('ATEM')
        tools_layout   = _make_tab('Test')
        access_layout  = _make_tab('Access')
        data_layout    = _make_tab('Data')
        root_layout.addWidget(tabs, stretch=1)

        build_test_tab(self, tools_layout, _panel_layout)

        # is_on is also read by the Cameras/ATEM blocks below, so keep it in
        # _build_ui scope even though build_session_tab recomputes its own.
        is_on = getattr(mw, 'session_active', False)
        build_session_tab(self, session_layout, mw, sim_active, _panel_layout)

        build_cameras_tab(self, cameras_layout, mw, is_on, sim_active, _panel_layout)

        # ── Sección: Operating Mode ──────────────────────────────────────
        build_access_tab(self, access_layout, mw, _panel_layout)

        build_data_tab(self, data_layout, mw, _panel_layout)

        build_atem_tab(self, atem_layout, mw, is_on, sim_active, _panel_layout)

        # ── Sección: Test Focus & Exposure ────────────────────────────────
        layout = _panel_layout(tools_layout, 'Focus & Exposure Test')

        # 7 indicadores: LED dot + label, cada uno en una card cell blanca (diseño test-grid)
        test_indicators = []
        ind_row = QHBoxLayout()
        ind_row.setSpacing(6)
        for label_text in ['AF', '1PAF', 'MF', 'Dark', 'Bright', 'BL', 'ATEM']:
            dot = self._led('off')
            test_indicators.append(dot)

            cap = QLabel(label_text.upper())
            cap.setAlignment(Qt.AlignCenter)
            cap.setStyleSheet(
                f"font: 700 9px 'Consolas', 'Courier New', monospace;"
                f" color: {_C_MUTED}; background: transparent; letter-spacing: 0.04em;"
            )

            cell_w = QFrame()
            cell_w.setObjectName("TestCell")
            cell_w.setStyleSheet(
                "QFrame#TestCell {"
                f"  background: white; border: 1px solid {_C_CARD_BD}; border-radius: 8px;"
                "}"
            )
            cell_layout = QVBoxLayout(cell_w)
            cell_layout.setContentsMargins(4, 10, 4, 10)
            cell_layout.setSpacing(7)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.addWidget(dot, alignment=Qt.AlignHCenter)
            cell_layout.addWidget(cap, alignment=Qt.AlignHCenter)

            ind_row.addWidget(cell_w, stretch=1)

        layout.addLayout(ind_row)

        btn_run_test = self._btn('Run Test', variant='primary', icon='play')
        layout.addWidget(btn_run_test, 0, Qt.AlignRight)

        # The ATEM reachability probe runs in a worker thread (socket connect can
        # block up to 3 s). Qt widgets must only be touched on the GUI thread, so
        # the result is delivered back via this signal.
        class _AtemTestSignal(QObject):
            done = pyqtSignal(bool)

        self._atem_test_sig = _AtemTestSignal()

        def _apply_atem_test(ok: bool):
            self._set_led(test_indicators[6], 'green' if ok else 'red')
            btn_run_test.setEnabled(True)
            btn_run_test.setText('Run Test')

        self._atem_test_sig.done.connect(_apply_atem_test)

        def _test_atem_connection():
            import config as _cfg
            if sim_active:
                import adapters.hardware_simulator as _hw
                _hw.atem_event_queue.put("switch_to_input2")
                ok = True
            else:
                try:
                    with socket.create_connection((_cfg.ATEM.ip, 9910), timeout=3):
                        ok = True
                except OSError as exc:
                    import logging as _log
                    _log.getLogger(__name__).warning("ATEM test failed: %s", exc)
                    ok = False
            self._atem_test_sig.done.emit(ok)

        def _on_test_clicked():
            for dot in test_indicators:
                self._set_led(dot, 'off')
            btn_run_test.setEnabled(False)
            btn_run_test.setText('Testing...')

            port = getattr(mw, '_camera_port', None)
            cam_id = "cam1" if getattr(mw, 'Cam1', None) and mw.Cam1.isChecked() else "cam2"

            # port_method_name → indicator index
            test_cmds = [
                ('focus_auto',       0),   # Auto Focus
                ('one_push_af',      1),   # One Push AF
                ('focus_manual',     2),   # Manual Focus
                ('brightness_down',  3),   # Darker
                ('brightness_up',    4),   # Brighter
                ('backlight_toggle', 5),   # Backlight ON
            ]

            def _after_visca():
                threading.Thread(target=_test_atem_connection, daemon=True).start()

            def _run_with_atem(step):
                if step >= len(test_cmds):
                    QTimer.singleShot(100, _after_visca)
                    return
                method_name, idx = test_cmds[step]
                if port is not None:
                    result = getattr(port, method_name)(cam_id)
                    ok = getattr(result, 'ok', False)
                else:
                    ok = False
                self._set_led(test_indicators[idx], 'green' if ok else 'red')
                QTimer.singleShot(500, lambda: _run_with_atem(step + 1))

            QTimer.singleShot(100, lambda: _run_with_atem(0))

        btn_run_test.clicked.connect(_on_test_clicked)

        # ── Sección: Preset Validation ────────────────────────────────────
        layout = _panel_layout(tools_layout, 'Preset Validation', badge_text='ADMIN')
        build_preset_validation_section(self, layout, mw)

        tools_layout.addStretch()

        # ── Footer (dlg-foot) ─────────────────────────────────────────────
        foot_widget = QWidget()
        foot_widget.setStyleSheet(
            f"background: #FAFAF9; border-top: 1px solid {_C_CARD_BD};"
            " border-bottom-left-radius: 14px; border-bottom-right-radius: 14px;"
        )
        foot_v = QVBoxLayout(foot_widget)
        foot_v.setContentsMargins(22, 14, 22, 18)
        foot_v.setSpacing(0)

        btn_close = QPushButton('✕  CLOSE PROGRAM')
        btn_close.setFixedHeight(44)
        btn_close.setStyleSheet(
            f"QPushButton {{ background: white; border: 1.5px solid {_C_ERROR_BD};"
            f" border-radius: 10px; font: 700 13px 'Inter Tight', 'Segoe UI';"
            f" color: {_C_ERROR}; letter-spacing: 0.06em; padding: 0 16px; }}"
            f"QPushButton:hover {{ background: {_C_ERROR}; border-color: {_C_ERROR};"
            " color: white; }"
            "QPushButton:pressed { background: #8E0F18; }"
        )
        btn_close.clicked.connect(mw.close)
        foot_v.addWidget(btn_close)
        root_layout.addWidget(foot_widget)

    # ── Status strip ─────────────────────────────────────────────────────────

    @staticmethod
    def _btn(text: str, variant: str = 'primary', height: int = 36,
             width: str = 'std', icon: Optional[str] = None) -> QPushButton:
        """Create a styled button matching the design spec (min-height=36, radius=9).

        width:
          'std' (default): fixed standard width (``_BTN_STD``) — uniform stand-alone
                 buttons; add them right-aligned (Qt.AlignRight) like the design.
          'row': expands to share a multi-button row equally.
        icon: optional key into ``_ICON_SVGS`` — a crisp line glyph placed left of
              the label and tinted to suit the variant (white on filled, slate on ghost).
        """
        from PyQt5.QtWidgets import QSizePolicy
        b = QPushButton(text)
        b.setMinimumHeight(height)
        b.setCursor(Qt.PointingHandCursor)
        if width == 'row':
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        else:
            b.setFixedWidth(_BTN_STD)
        if icon and icon in _ICON_SVGS:
            tint = _ICON_TINT.get(variant, _C_SECONDARY)
            b.setIcon(_svg_icon_markup(_ICON_SVGS[icon], 14, color=tint))
            b.setIconSize(QSize(14, 14))
        # padding-left smaller when an icon is present so glyph+label stay centred
        _pad = "5px 14px 5px 12px" if icon else "5px 14px"
        _font = "font: 600 13px 'Inter Tight', 'Segoe UI'; letter-spacing: 0.005em;"
        if variant == 'primary':
            b.setStyleSheet(
                f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f" stop:0 {_C_BRAND_MID}, stop:1 {_C_BRAND_DARK});"
                f" border: none; border-radius: 9px; {_font} color: white;"
                f" padding: {_pad}; }}"
                "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #3a6633, stop:1 #223d20); }"
                "QPushButton:pressed { background: #1A3318; }"
                "QPushButton:disabled { background: #90A4AE; }"
            )
        elif variant == 'ghost':
            b.setStyleSheet(
                f"QPushButton {{ background: white; border: 1px solid #DCDEDB;"
                f" border-radius: 9px; {_font} color: {_C_SECONDARY}; padding: {_pad}; }}"
                f"QPushButton:hover {{ background: #F6F7F5; border-color: #C8CAC6;"
                f" color: {_C_BRAND_DARK}; }}"
                "QPushButton:pressed { background: #EBEBEB; }"
                "QPushButton:disabled { background: #F4F5F3; color: #999; }"
            )
        elif variant == 'danger':
            b.setStyleSheet(
                f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f" stop:0 {_C_ERROR}, stop:1 #8E0F18);"
                f" border: none; border-radius: 9px; {_font} color: white; padding: {_pad}; }}"
                "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #d41828, stop:1 #a01020); }"
                "QPushButton:pressed { background: #6E080F; }"
                "QPushButton:disabled { background: #90A4AE; }"
            )
        elif variant == 'info':
            b.setStyleSheet(
                f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #1976D2, stop:1 #0D5FA3);"
                f" border: none; border-radius: 9px; {_font} color: white; padding: {_pad}; }}"
                "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #2080dc, stop:1 #1468b0); }"
                "QPushButton:pressed { background: #0A4A80; }"
                "QPushButton:disabled { background: #90A4AE; }"
            )
        return b

    @staticmethod
    def _badge(text: str, kind: str = 'muted') -> QLabel:
        """Create a badge pill label."""
        lbl = QLabel(text.upper())
        _styles = {
            'ok':   (f'background: {_C_SUCCESS_BG}; color: {_C_SUCCESS};'
                     f' border: 1px solid {_C_SUCCESS_BD};'),
            'warn': (f'background: {_C_WARNING_BG}; color: {_C_WARNING};'
                     f' border: 1px solid {_C_WARNING_BD};'),
            'muted': ('background: #F4F5F3; color: #666666;'
                      ' border: 1px solid #E0E2DE;'),
        }
        style = _styles.get(kind, _styles['muted'])
        lbl.setStyleSheet(
            f"{style}"
            " border-radius: 999px; padding: 2px 8px;"
            " font: 700 10px 'Consolas', 'Courier New', monospace;"
            " letter-spacing: 0.06em;"
        )
        return lbl

    @staticmethod
    def _set_online_badge(badge: Optional[QLabel], online: bool) -> None:
        """Re-style an existing camera Online/Offline badge in place.

        Mirrors the text and colours produced by ``_badge`` so a live
        connectivity re-check can flip the pill without rebuilding the card.
        """
        if badge is None:
            return
        text = 'Online' if online else 'Offline'
        if online:
            style = (f'background: {_C_SUCCESS_BG}; color: {_C_SUCCESS};'
                     f' border: 1px solid {_C_SUCCESS_BD};')
        else:
            style = (f'background: {_C_WARNING_BG}; color: {_C_WARNING};'
                     f' border: 1px solid {_C_WARNING_BD};')
        try:
            badge.setText(text.upper())
            badge.setStyleSheet(
                f"{style}"
                " border-radius: 999px; padding: 2px 8px;"
                " font: 700 10px 'Consolas', 'Courier New', monospace;"
                " letter-spacing: 0.06em;"
            )
        except RuntimeError:
            pass  # widget already deleted

    @staticmethod
    def _status_pill(text: str, state: str = 'ok', meta: Optional[str] = None) -> QWidget:
        """Create a status pill with LED dot."""
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(12, 6, 14, 6)
        h.setSpacing(8)

        _led_state = {'ok': 'green', 'warn': 'amber', 'error': 'red', 'neutral': 'off'}
        pill_styles = {
            'ok':      (f'{_C_SUCCESS_BG}', 'rgba(27,127,62,.30)',  _C_SUCCESS),
            'warn':    (f'{_C_WARNING_BG}', 'rgba(184,79,0,.30)',   _C_WARNING),
            'error':   (f'{_C_ERROR_BG}',   'rgba(192,20,31,.30)', _C_ERROR),
            'neutral': ('#F4F5F3',          '#E6E8E5',               _C_SECONDARY),
        }
        bg, bd, fg = pill_styles.get(state, pill_styles['neutral'])

        wrap.setStyleSheet(
            f"background: {bg}; border: 1px solid {bd};"
            " border-radius: 8px;"
        )

        led = ConfigDialog._led(_led_state.get(state, 'off'))
        h.addWidget(led)

        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"font: 600 13px 'Inter Tight', 'Segoe UI'; color: {fg};"
            " background: transparent;"
        )
        h.addWidget(lbl)
        h.addStretch()

        if meta:
            # Design: `.status .meta { margin-left:auto }` — pushed to the right
            # edge of the pill and set in the mono (data) typeface.
            meta_lbl = QLabel(meta)
            meta_lbl.setStyleSheet(
                "font: 500 11px 'Consolas', 'Courier New', monospace;"
                f" color: {fg}; background: transparent;"
            )
            h.addWidget(meta_lbl)

        return wrap

    @staticmethod
    def _field_row(label: str, value_text: str, on_edit=None) -> QWidget:
        """Create a 3-column field row: label | value | edit-button.

        Matches the design spec: field-label (62px, mono, uppercase) | field-value
        (mono, bg chip) | icon-btn (32px).  A 1px top border is applied by the
        caller card body for all rows after the first.
        """
        wrap = QWidget()
        wrap.setObjectName('FieldRow')
        h = QHBoxLayout(wrap)
        h.setContentsMargins(2, 7, 2, 7)
        h.setSpacing(10)

        lbl = QLabel(label.upper())
        lbl.setFixedWidth(62)
        lbl.setStyleSheet(
            "font: 700 10px 'Consolas', 'Courier New', monospace;"
            f" color: {_C_MUTED}; letter-spacing: 0.08em; background: transparent;"
        )
        h.addWidget(lbl)

        val = QLabel(value_text)
        val.setObjectName('field_value')
        val.setStyleSheet(
            f"font: 500 13px 'Consolas', 'Courier New', monospace; color: {_C_BRAND_DARK};"
            f" background: {_C_FIELD_BG}; border: 1px solid {_C_FIELD_BD};"
            " border-radius: 6px; padding: 8px 10px; letter-spacing: 0.02em;"
        )
        h.addWidget(val, stretch=1)

        btn = QPushButton()
        _edit_svg = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'edit.svg')
        btn.setIcon(_svg_icon(_edit_svg, 15, color='#555555'))
        btn.setIconSize(QSize(15, 15))
        btn.setFixedSize(32, 32)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background: white; border: 1px solid #DCDEDB;"
            " border-radius: 7px; }"
            "QPushButton:hover { background: rgba(46,82,41,0.08);"
            " border-color: rgba(46,82,41,0.28); }"
            "QPushButton:pressed { background: #EBEBEB; }"
        )
        if on_edit:
            btn.clicked.connect(on_edit)
        h.addWidget(btn)

        return wrap

    @staticmethod
    def _set_led(label: QLabel, state: str) -> None:
        """Set *label*'s pixmap to a round LED in the given state.

        state ∈ {'green','red','amber','off'}. Works on the QLabel created by
        ``_led`` so dynamic indicators (ATEM, test grid) update cleanly.
        """
        label.setPixmap(_led_pixmap(state))

    @staticmethod
    def _led(color: str = 'green') -> QLabel:
        """Create a round LED indicator dot (QLabel showing a painted pixmap)."""
        lbl = QLabel()
        lbl.setObjectName('led_dot')
        lbl.setFixedSize(_LED_SIZE, _LED_SIZE)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("background: transparent; border: none;")
        ConfigDialog._set_led(lbl, color)
        return lbl

    @staticmethod
    def _info_line(key: str, val: str) -> QWidget:
        """Create an info-line row: key on left, monospace value chip on right."""
        wrap = QWidget()
        h = QHBoxLayout(wrap)
        h.setContentsMargins(10, 7, 10, 7)
        h.setSpacing(10)
        wrap.setStyleSheet(
            "background: #F4F5F3; border: 1px solid #EBEDE9; border-radius: 8px;"
        )
        key_lbl = QLabel(key)
        key_lbl.setStyleSheet(
            f"font: 400 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
            " background: transparent;"
        )
        h.addWidget(key_lbl)
        h.addStretch()
        val_lbl = QLabel(val)
        val_lbl.setStyleSheet(
            f"font: 600 11px 'Consolas', 'Courier New', monospace; color: {_C_BRAND_DARK};"
            " background: white; border: 1px solid #E0E2DE; border-radius: 5px;"
            " padding: 3px 8px; letter-spacing: 0.04em;"
        )
        h.addWidget(val_lbl)
        return wrap

    @staticmethod
    def _cam_panel(parent_layout, cam_label: str, cam_num: int, accent: str,
                   online: bool | None = None):
        """Build a camera card with cam-name + cam-tag pill + online badge header.

        Returns ``(body_layout, online_badge)``. ``online_badge`` is the QLabel
        pill so callers can refresh it live after a connectivity re-check; it is
        ``None`` only when ``online`` is None (state unknown, no badge shown).
        """
        from PyQt5.QtWidgets import QVBoxLayout as _QVL
        tag_color = '#9B3A3A' if cam_label == 'Platform' else '#4A8C4A'
        tag_bg    = 'rgba(155,58,58,0.10)' if cam_label == 'Platform' else 'rgba(74,140,74,0.10)'
        tag_bd    = 'rgba(155,58,58,0.20)' if cam_label == 'Platform' else 'rgba(74,140,74,0.20)'

        card = QFrame()
        card.setObjectName("ConfigCard")
        card.setStyleSheet(
            "QFrame#ConfigCard {"
            f"  border: 1px solid {_C_CARD_BD};"
            "  border-radius: 12px;"
            "  background: #FCFCFB;"
            f"  border-left: 3px solid {accent};"
            "}"
        )
        card_v = _QVL(card)
        card_v.setContentsMargins(0, 0, 0, 0)
        card_v.setSpacing(0)

        card_head = QWidget()
        card_head.setStyleSheet(
            f"background: white; border-bottom: 1px solid {_C_CARD_BD};"
            " border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        head_row = QHBoxLayout(card_head)
        head_row.setContentsMargins(16, 10, 16, 10)
        head_row.setSpacing(8)

        cam_name_lbl = QLabel(cam_label)
        cam_name_lbl.setStyleSheet(
            f"font: 700 13px 'Inter Tight', 'Segoe UI'; color: {_C_BRAND_DARK};"
            " background: transparent;"
        )
        head_row.addWidget(cam_name_lbl)

        cam_tag_lbl = QLabel(f'Cam {cam_num}')
        cam_tag_lbl.setStyleSheet(
            f"font: 600 10px 'Consolas', 'Courier New', monospace; color: {tag_color};"
            f" background: {tag_bg}; border: 1px solid {tag_bd};"
            " border-radius: 999px; padding: 2px 7px; letter-spacing: 0.10em;"
        )
        head_row.addWidget(cam_tag_lbl)
        head_row.addStretch()

        online_badge = None
        if online is not None:
            badge_text  = 'Online'  if online else 'Offline'
            badge_kind  = 'ok'      if online else 'warn'
            online_badge = ConfigDialog._badge(badge_text, badge_kind)
            head_row.addWidget(online_badge)

        card_v.addWidget(card_head)

        body_w = QWidget()
        body_w.setStyleSheet("background: transparent;")
        body_layout = _QVL(body_w)
        body_layout.setContentsMargins(14, 0, 14, 12)
        body_layout.setSpacing(0)  # separators handle visual gaps
        card_v.addWidget(body_w)

        parent_layout.addWidget(card)
        return body_layout, online_badge

    # ── Legacy style helper (kept for _build_sim_section) ─────────────────────

    def _section_label(self, text: str) -> QLabel:
        """Etiqueta de sección con estilo consistente."""
        lbl = QLabel(text)
        lbl.setStyleSheet("font: bold 16px 'Inter Tight', 'Segoe UI'; color: #222; padding-top: 2px;")
        return lbl

    @staticmethod
    def _disconnect_signal(signal, slot) -> None:
        try:
            signal.disconnect(slot)
        except TypeError:
            pass

    @staticmethod
    def _current_runtime_mode(sim_active: bool) -> str:
        """Devuelve el perfil efectivo mostrado por la pantalla técnica."""
        profile = os.environ.get("KHPTZ_PROFILE", "production").strip().lower()
        if profile in {"demo", "simulation"}:
            return profile
        return "simulation" if sim_active else "production"

    @staticmethod
    def _runtime_mode_button_style(mode: str) -> str:
        colors = {
            "production": ("#455A64", "#263238"),
            "demo": ("#4A7A44", "#2E5229"),
            "simulation": ("#4A7A44", "#2E5229"),
        }
        bg, pressed = colors[mode]
        return (
            f"QPushButton {{ background: {bg}; border: none; border-radius: 6px;"
            " font: bold 13px; color: white; }"
            f"QPushButton:pressed {{ background: {pressed}; }}"
        )

    def _restart_in_runtime_mode(self, mw, target_mode: str) -> None:
        """Reinicia la aplicación con el perfil solicitado."""
        from PyQt5.QtWidgets import QMessageBox

        title = f"Restart in {target_mode.title()} Mode"
        details = {
            "production": "The app will disable local simulation and restart with production data.",
            "demo": "The app will reset demo data, enable local simulation, and restart.",
            "simulation": "The app will enable local simulation and restart with isolated test data.",
        }
        reply = QMessageBox.question(
            self,
            title,
            f"{details[target_mode]}\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        demo_dir = Path.home() / ".config" / "khptz-demo"

        if target_mode == "production":
            try:
                if _sim_mode.is_active():
                    _sim_mode.deactivate()
            except RuntimeError as exc:
                QMessageBox.warning(
                    self,
                    title,
                    str(exc) or "Could not disable simulation mode.",
                )
                return
        else:
            try:
                if not _sim_mode.is_active():
                    _sim_mode.activate()
            except RuntimeError as exc:
                QMessageBox.warning(
                    self,
                    title,
                    str(exc) or "Could not enable simulation mode.",
                )
                return

            if target_mode == "demo":
                try:
                    from application.demo_reset_service import DemoResetService

                    result = DemoResetService(demo_data_dir=demo_dir).reset()
                except Exception as exc:
                    QMessageBox.warning(
                        self,
                        title,
                        f"Could not reset demo data:\n{exc}",
                    )
                    return

                if not result.success:
                    QMessageBox.warning(
                        self,
                        title,
                        result.error or "Could not reset demo data.",
                    )
                    return

        env = os.environ.copy()
        env["KHPTZ_PROFILE"] = target_mode
        if target_mode in {"demo", "simulation"}:
            env["KHPTZ_DATA_DIR"] = str(demo_dir)
        elif Path(env.get("KHPTZ_DATA_DIR", "")).expanduser() == demo_dir:
            env.pop("KHPTZ_DATA_DIR", None)

        main_path = Path(__file__).with_name("main.py")
        try:
            subprocess.Popen(
                [sys.executable, str(main_path)],
                cwd=str(main_path.parent),
                env=env,
                close_fds=True,
            )
        except OSError as exc:
            QMessageBox.warning(
                self,
                title,
                f"Could not launch {target_mode} mode:\n{exc}",
            )
            return

        self.close()
        mw.close()


    def _toast(self, message: str, kind: str = 'ok', duration: int = 2800) -> None:
        """Show a brief, non-modal confirmation that auto-dismisses.

        Lighter than a QMessageBox for simple "done" feedback (saved, exported…).
        kind ∈ {'ok','warn','error','info'}.
        """
        from PyQt5.QtCore import QTimer
        _styles = {
            'ok':    (_C_SUCCESS_BG, _C_SUCCESS_BD, _C_SUCCESS),
            'warn':  (_C_WARNING_BG, _C_WARNING_BD, _C_WARNING),
            'error': (_C_ERROR_BG,   _C_ERROR_BD,   _C_ERROR),
            'info':  ('#E8F2FC',     'rgba(13,95,163,0.28)', '#0D5FA3'),
        }
        bg, bd, fg = _styles.get(kind, _styles['ok'])
        if getattr(self, '_toast_lbl', None) is None:
            self._toast_lbl = QLabel(self)
            self._toast_lbl.setAlignment(Qt.AlignCenter)
            self._toast_lbl.setWordWrap(True)
            self._toast_timer = QTimer(self)
            self._toast_timer.setSingleShot(True)
            self._toast_timer.timeout.connect(self._toast_lbl.hide)
        t = self._toast_lbl
        t.setStyleSheet(
            f"background: {bg}; border: 1px solid {bd}; border-radius: 10px;"
            f" color: {fg}; font: 600 13px 'Inter Tight', 'Segoe UI'; padding: 11px 18px;"
        )
        t.setText(message)
        t.adjustSize()
        w = min(max(t.width(), 220), self.width() - 60)
        t.setFixedWidth(w)
        t.adjustSize()
        t.move((self.width() - t.width()) // 2, self.height() - t.height() - 92)
        t.show()
        t.raise_()
        self._toast_timer.stop()
        self._toast_timer.start(duration)

    def _confirm_danger(self, title: str, text: str, action_label: str) -> bool:
        """Modal confirm for a destructive action.

        The dangerous button is red; Cancel is the default/escape button so a
        stray Enter or tap never triggers the destructive path. Returns True
        only if the user explicitly chose the dangerous action.
        """
        from PyQt5.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(title)
        box.setText(text)
        act = box.addButton(action_label, QMessageBox.AcceptRole)
        cancel = box.addButton('Cancel', QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        act.setStyleSheet(
            "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f" stop:0 {_C_ERROR}, stop:1 #8E0F18); border: none; border-radius: 9px;"
            " padding: 7px 16px; min-width: 90px; min-height: 36px;"
            " font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; }"
            "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            " stop:0 #d41828, stop:1 #a01020); }"
        )
        box.exec_()
        return box.clickedButton() is act

    @staticmethod
    def _lock_if_live(widget, is_live: bool,
                      reason: str = 'Disabled during a live session',
                      dim_target=None) -> None:
        """Disable a dangerous control while a session is running (with a why).

        Besides disabling the control we dim it (opacity 0.4) so the locked
        state is obvious on the touchscreen, where there is no hover tooltip
        to reveal *why* the control does nothing. ``dim_target`` lets the
        caller fade a whole field row (label + value + edit button) instead of
        just the button. The accompanying banner (see _session_lock_banner)
        tells the operator to stop the session.
        """
        if is_live:
            widget.setEnabled(False)
            widget.setToolTip(reason)
            faded = dim_target if dim_target is not None else widget
            effect = QGraphicsOpacityEffect(faded)
            effect.setOpacity(0.4)
            faded.setGraphicsEffect(effect)

    @staticmethod
    def _session_lock_banner(text: str) -> QWidget:
        """Amber notice shown above controls that are locked during a session."""
        banner = QLabel('🔒  ' + text)
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"font: 600 12px 'Inter Tight', 'Segoe UI'; color: {_C_WARNING};"
            f" background: {_C_WARNING_BG}; border: 1px solid {_C_WARNING_BD};"
            f" border-radius: 8px; padding: 8px 12px;"
        )
        return banner

    def _try_close(self):
        """Cierra ConfigDialog tras cambio de contraseña."""
        self.accept()
