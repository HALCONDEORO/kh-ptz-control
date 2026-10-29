#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# splash_screen.py — Pantalla de inicialización

from __future__ import annotations

import logging
import socket
import binascii
import threading
import time
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import ClassVar

logger = logging.getLogger(__name__)

CAMERA_STARTUP_TIMEOUT_SECONDS = 10

from application.camera_discovery import get_camera_subnet, tcp_scan, arp_scan
from runtime.path_resolver import RuntimePathResolver as _RuntimePathResolver

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt5.QtGui import (
    QFont, QPainter, QColor, QRadialGradient, QPen, QBrush
)

from config import CAM1, CAM2, SOCKET_TIMEOUT, VISCA_PORT, SEAT_POSITIONS
import adapters.sim_mode as _sim_mode

# TestResult y BootStatistics (Python puro, sin Qt) viven en
# application/boot_metrics.py. Se re-exportan aquí para mantener compatibilidad
# con `from ui.splash_screen import TestResult, BootStatistics`.
from application.boot_metrics import TestResult, BootStatistics  # noqa: F401

from app_version import APP_NAME, read_version as _read_version
from ui.fitting_label import FittingTitleLabel
from application.schedule_config import load_schedule, DAYS as _SCHED_DAYS

_APP_VERSION: str = _read_version()
_HOSTNAME: str = socket.gethostname()


def _get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(0)
            s.connect(('10.254.254.254', 1))
            return s.getsockname()[0]
    except Exception:
        return 'unknown'


_LOCAL_IP: str = _get_local_ip()


# ═══════════════════════════════════════════════════════════════════════════════
#  TICKER DE TESTS — lista rodante una línea por resultado
# ═══════════════════════════════════════════════════════════════════════════════

class TestTickerWidget(QWidget):
    """
    Muestra los resultados de los tests como filas individuales que van
    apareciendo desde abajo con una animación de deslizamiento.
    Cada fila: nombre alineado a la izquierda, marca ✓/✗ a la derecha.
    """

    _ROW_H    = 20   # altura de cada fila en píxeles
    _MAX_ROWS = 3    # filas visibles simultáneamente
    _STEPS    = 6    # pasos de la animación slide-in

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(440)
        self.setFixedHeight(self._MAX_ROWS * self._ROW_H)
        self._entries: list[tuple[str, bool]] = []
        self._slide = 0   # desplazamiento vertical actual de la animación

        self._timer = QTimer(self)
        self._timer.setInterval(18)   # ~55 fps
        self._timer.timeout.connect(self._advance)

    def add_result(self, name: str, success: bool):
        self._entries.append((name, success))
        self._slide = self._ROW_H          # nueva entrada empieza fuera de vista (abajo)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def _advance(self):
        if self._slide > 0:
            self._slide = max(0, self._slide - 3)
            self.update()
        else:
            self._timer.stop()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setClipRect(0, 0, self.width(), self.height())

        font = QFont('IBM Plex Mono', 11)
        p.setFont(font)

        # Mostrar las últimas MAX_ROWS+1 entradas (una extra para la animación)
        visible = self._entries[-(self._MAX_ROWS + 1):]
        n = len(visible)

        for idx, (name, success) in enumerate(visible):
            rows_from_bottom = n - 1 - idx   # 0 = más reciente (abajo)
            y = self.height() - (rows_from_bottom + 1) * self._ROW_H + self._slide

            if y + self._ROW_H < 0:
                continue   # salió por arriba

            # Opacidad: la más reciente brilla, las antiguas se atenúan
            age = rows_from_bottom
            alpha = 210 if age == 0 else max(45, 160 - age * 38)

            row_rect = QRect(0, y, self.width(), self._ROW_H)

            # Nombre — izquierda
            p.setPen(QColor(255, 255, 255, alpha))
            p.drawText(row_rect, Qt.AlignLeft | Qt.AlignVCenter, name)

            # Marca — derecha
            if success:
                p.setPen(QColor(35, 170, 70, alpha))
                p.drawText(row_rect, Qt.AlignRight | Qt.AlignVCenter, '✓')
            else:
                p.setPen(QColor(190, 35, 35, alpha))
                p.drawText(row_rect, Qt.AlignRight | Qt.AlignVCenter, '✗')

        p.end()


# ═══════════════════════════════════════════════════════════════════════════════
#  PANTALLA DE SPLASH
# ═══════════════════════════════════════════════════════════════════════════════

class SplashScreen(QWidget):
    """
    Pantalla de inicialización con tests paralelos y carga adaptativa.

    Siempre emite startup_complete al terminar, con o sin cámaras.
    startup_failed se conserva para errores verdaderamente fatales (no usados
    actualmente; el flujo de main.py ya no los requiere).
    """

    startup_complete = pyqtSignal()

    # Señales internas para actualizar UI de forma thread-safe.
    # Qt enruta señales emitidas desde hilos de fondo al hilo principal
    # automáticamente con conexión QueuedConnection.
    _sig_log          = pyqtSignal(str)
    _sig_status       = pyqtSignal(str, str)    # mensaje, color
    _sig_progress     = pyqtSignal(int)         # 0-100
    _sig_cam_update   = pyqtSignal(int, str)    # cam_idx (1/2), estado
    _sig_ticker       = pyqtSignal(str, bool)   # nombre_corto, éxito
    _sig_interrupted  = pyqtSignal(str)         # timestamp de la sesión interrumpida
    _sig_chip_update  = pyqtSignal(str, bool)   # chip_name, ok
    _sig_schedule_text = pyqtSignal(str, str)   # texto, color_key
    _sig_boot_footer  = pyqtSignal(str)         # texto para footer de boots

    # Nombres completos de días de la semana (índice 0=lunes, 6=domingo)
    _DAY_NAMES = (
        'Monday', 'Tuesday', 'Wednesday',
        'Thursday', 'Friday', 'Saturday', 'Sunday',
    )

    # Estilos por estado de cámara/dispositivo
    _CAM_STATE: ClassVar[dict] = {
        'connecting': {
            'border': 'rgba(212,134,10,0.30)',
            'bg':     'rgba(212,134,10,0.05)',
            'led':    '#D4860A',
            'glow':   (212, 134, 10),
            'text':   '#D4860A',
            'label':  'Connecting...',
        },
        'connected': {
            'border': 'rgba(35,170,70,0.30)',
            'bg':     'rgba(35,170,70,0.06)',
            'led':    '#23AA46',
            'glow':   (35, 170, 70),
            'text':   '#23AA46',
            'label':  'Connected',
        },
        'disconnected': {
            'border': 'rgba(190,35,35,0.30)',
            'bg':     'rgba(190,35,35,0.05)',
            'led':    '#BE2323',
            'glow':   (190, 35, 35),
            'text':   '#BE2323',
            'label':  'No response',
        },
    }


    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(False)

        self.tests_passed    = 0
        self.tests_total     = 0
        self.test_results: dict = {}
        self.boot_start_time = time.time()
        self.diagnostic_mode = False
        self._cam1_status    = 'connecting'
        self._cam2_status    = 'connecting'
        self._led_pulse_on   = True

        _boot_stats_path = _RuntimePathResolver().data_dir / "boot_stats.json"
        self.boot_stats = BootStatistics(stats_file=str(_boot_stats_path))

        self._build_ui()

        # Conectar señales internas → slots en hilo principal
        self._sig_log.connect(self._do_log)
        self._sig_status.connect(self._do_status)
        self._sig_progress.connect(self.progress_bar.setValue)
        self._sig_cam_update.connect(self._do_cam_update)
        self._sig_ticker.connect(self._do_ticker)
        self._sig_interrupted.connect(self._do_show_interrupted)
        self._sig_chip_update.connect(self._do_chip_update)
        self._sig_schedule_text.connect(self._do_schedule_text)
        self._sig_boot_footer.connect(self._do_boot_footer)

        # Pulso para LEDs en estado "connecting"
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_leds)
        self._pulse_timer.start(600)


        # Reloj en vivo (dispara en hilo principal, sin señal)
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._tick_clock()  # actualización inmediata al arrancar

    # ─────────────────────────────────────────────────────────────────────────
    #  BACKGROUND
    # ─────────────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Fondo sólido #1A1F19
        p.fillRect(0, 0, w, h, QColor(0x1A, 0x1F, 0x19))

        # Radial verde suave centrado (70% × 60% del canvas, a 50% / 40%)
        glow = QRadialGradient(w * 0.50, h * 0.40, max(w, h) * 0.55)
        glow.setColorAt(0.0, QColor(46, 82, 41, 76))   # rgba 0.30
        glow.setColorAt(1.0, QColor(46, 82, 41, 0))
        p.fillRect(0, 0, w, h, QBrush(glow))

        # Radial verde oscuro, esquina inferior-izquierda
        accent = QRadialGradient(w * 0.20, h * 0.80, max(w, h) * 0.38)
        accent.setColorAt(0.0, QColor(26, 51, 24, 51))  # rgba 0.20
        accent.setColorAt(1.0, QColor(26, 51, 24, 0))
        p.fillRect(0, 0, w, h, QBrush(accent))

        # Grid 80×80 px, rgba(255,255,255,0.015)
        grid_pen = QPen(QColor(255, 255, 255, 4))
        grid_pen.setWidth(1)
        p.setPen(grid_pen)
        for x in range(0, w, 80):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 80):
            p.drawLine(0, y, w, y)

        p.end()

    # ─────────────────────────────────────────────────────────────────────────
    #  UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Contenido central ─────────────────────────────────────────────
        center = QWidget()
        center.setFixedWidth(620)
        center.setAttribute(Qt.WA_TranslucentBackground)
        col = QVBoxLayout(center)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.setAlignment(Qt.AlignHCenter)

        # ── Header: logo centrado + reloj a la derecha ─────────────────
        # El left_pad contrarresta el clock_container para mantener el logo
        # visualmente centrado en los 620px. Sin él el logo queda ~80px a la izquierda.
        col.addSpacing(44)

        logo = QLabel('PTZ')
        logo.setFixedSize(88, 88)
        logo.setAlignment(Qt.AlignCenter)
        logo.setFont(QFont('Inter Tight', 22, QFont.Bold))
        logo.setStyleSheet(
            "QLabel {"
            "  color: rgba(255,255,255,0.85);"
            "  background: qlineargradient(x1:0.15,y1:0,x2:0.85,y2:1,"
            "    stop:0 #4A7A44, stop:1 #1A3318);"
            "  border-radius: 22px;"
            "  border: 1px solid rgba(255,255,255,0.10);"
            "  letter-spacing: 3px;"
            "}"
        )
        logo_glow = QGraphicsDropShadowEffect(logo)
        logo_glow.setBlurRadius(28)
        logo_glow.setColor(QColor(35, 170, 70, 90))
        logo_glow.setOffset(0, 0)
        logo.setGraphicsEffect(logo_glow)

        # Contrapeso izquierdo (misma anchura que clock_container)
        _left_pad = QWidget()
        _left_pad.setFixedWidth(160)
        _left_pad.setAttribute(Qt.WA_TranslucentBackground)

        # Reloj: columna derecha alineada arriba
        clock_container = QWidget()
        clock_container.setAttribute(Qt.WA_TranslucentBackground)
        clock_container.setFixedWidth(160)
        clock_col_layout = QVBoxLayout(clock_container)
        clock_col_layout.setContentsMargins(0, 6, 0, 0)
        clock_col_layout.setSpacing(2)
        clock_col_layout.setAlignment(Qt.AlignRight | Qt.AlignTop)

        self._clock_label = QLabel('--:--:--')
        self._clock_label.setFont(QFont('IBM Plex Mono', 22, QFont.Bold))
        self._clock_label.setStyleSheet(
            "color: rgba(255,255,255,0.88); background: transparent; letter-spacing: -1px;"
        )
        self._clock_label.setAlignment(Qt.AlignRight)

        self._date_label = QLabel('--')
        self._date_label.setFont(QFont('Inter Tight', 12))
        self._date_label.setStyleSheet(
            "color: rgba(255,255,255,0.38); background: transparent;"
        )
        self._date_label.setAlignment(Qt.AlignRight)

        clock_col_layout.addWidget(self._clock_label)
        clock_col_layout.addWidget(self._date_label)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(0)
        header_row.addWidget(_left_pad)   # contrapeso → logo centrado
        header_row.addStretch()
        header_row.addWidget(logo)
        header_row.addStretch()
        header_row.addWidget(clock_container)
        col.addLayout(header_row)
        col.addSpacing(20)

        # ── Título ────────────────────────────────────────────────────────
        title = FittingTitleLabel(APP_NAME)
        title.setStyleSheet("color: #FFFFFF; background: transparent; letter-spacing: -2px;")
        title.setAlignment(Qt.AlignCenter)
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        col.addWidget(title)
        col.addSpacing(8)

        # ── Subtítulo (estado) ────────────────────────────────────────────
        self.subtitle_label = QLabel('Initializing camera connections...')
        self.subtitle_label.setFont(QFont('Inter Tight', 16))
        self.subtitle_label.setStyleSheet(
            "color: rgba(255,255,255,102); background: transparent;"
        )
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        col.addWidget(self.subtitle_label)
        col.addSpacing(10)

        # ── Banner de sesión interrumpida (oculto por defecto) ────────────
        self._interrupted_banner = QFrame()
        self._interrupted_banner.setObjectName("interrupted_banner")
        self._interrupted_banner.setFrameShape(QFrame.NoFrame)
        self._interrupted_banner.setFixedHeight(44)
        self._interrupted_banner.setStyleSheet(
            "QFrame#interrupted_banner {"
            "  background: rgba(212,134,10,0.12);"
            "  border: 1px solid rgba(212,134,10,0.40);"
            "  border-radius: 10px;"
            "}"
        )
        banner_layout = QHBoxLayout(self._interrupted_banner)
        banner_layout.setContentsMargins(18, 0, 18, 0)
        banner_layout.setSpacing(10)
        banner_icon = QLabel('!')
        banner_icon.setFont(QFont('Inter Tight', 14, QFont.Bold))
        banner_icon.setStyleSheet("color: #D4860A; background: transparent;")
        banner_icon.setFixedWidth(18)
        banner_icon.setAlignment(Qt.AlignCenter)
        self._interrupted_lbl = QLabel(
            'Previous session interrupted — check cameras before starting'
        )
        self._interrupted_lbl.setFont(QFont('Inter Tight', 13))
        self._interrupted_lbl.setStyleSheet("color: #D4860A; background: transparent;")
        banner_layout.addWidget(banner_icon)
        banner_layout.addWidget(self._interrupted_lbl)
        banner_layout.addStretch()
        self._interrupted_banner.setVisible(False)
        col.addWidget(self._interrupted_banner)
        col.addSpacing(8)

        # ── Panel de horario de hoy ────────────────────────────────────────
        # Populated immediately (sync) so the operator sees the schedule at once,
        # then confirmed/overwritten by the background phase-1 signal.
        self._schedule_label = QLabel('')
        self._schedule_label.setFont(QFont('Inter Tight', 13))
        self._schedule_label.setStyleSheet(
            "color: rgba(255,255,255,0.38); background: transparent;"
        )
        self._schedule_label.setAlignment(Qt.AlignCenter)
        self._apply_schedule_display()   # read schedule.json now, not after phase 1
        col.addWidget(self._schedule_label)
        col.addSpacing(14)

        # ── Tarjetas de cámara (280px c/u, gap 20px) ─────────────────────
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)
        cards_row.setContentsMargins(0, 0, 0, 0)
        self._cam1_card = self._make_cam_card(
            1, 'Camera 1', 'Platform', 'Chairman / Lectern area', CAM1.ip, 'connecting'
        )
        self._cam2_card = self._make_cam_card(
            2, 'Camera 2', 'Comments', 'Auditorium seating area', CAM2.ip, 'connecting'
        )
        cards_row.addWidget(self._cam1_card)
        cards_row.addWidget(self._cam2_card)
        col.addLayout(cards_row)
        col.addSpacing(10)

        # ── Chips de datos ─────────────────────────────────────────────────
        chips_row = QHBoxLayout()
        chips_row.setSpacing(10)
        chips_row.setContentsMargins(0, 0, 0, 0)
        chips_row.addStretch()
        self._chip_labels: dict[str, QLabel] = {}
        for chip_name in ('seat names', 'schedule', 'presets'):
            chip = self._make_chip(chip_name)
            self._chip_labels[chip_name] = chip
            chips_row.addWidget(chip)
        chips_row.addStretch()
        col.addLayout(chips_row)
        col.addSpacing(16)

        # ── Barra de progreso + ticker ────────────────────────────────────
        bar_wrap = QWidget()
        bar_wrap.setFixedWidth(440)
        bar_wrap.setAttribute(Qt.WA_TranslucentBackground)
        bar_col = QVBoxLayout(bar_wrap)
        bar_col.setContentsMargins(0, 0, 0, 0)
        bar_col.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 2px;
                background-color: rgba(255,255,255,18);
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2E5229, stop:0.5 #4A7A44, stop:1 #23AA46);
                border-radius: 2px;
            }
        """)
        self.progress_bar.setValue(0)
        bar_col.addWidget(self.progress_bar)

        # Ticker de tests — lista rodante con animación slide-in
        self.ticker_widget = TestTickerWidget()
        bar_col.addWidget(self.ticker_widget)

        bar_row = QHBoxLayout()
        bar_row.addStretch()
        bar_row.addWidget(bar_wrap)
        bar_row.addStretch()
        col.addLayout(bar_row)

        # Buffer interno para el log (no visible)
        self.log_label = QLabel('')
        self.log_label.hide()
        col.addWidget(self.log_label)

        root.addStretch()
        root.addWidget(center, 0, Qt.AlignHCenter)
        root.addStretch()

        # ── Footer absoluto ───────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(48, 0, 48, 36)
        footer.setSpacing(0)

        org_lbl = QLabel('Hall PTZ Control')
        org_lbl.setFont(QFont('Inter Tight', 13))
        org_lbl.setStyleSheet("color: rgba(255,255,255,51); background: transparent;")

        self._boot_count_label = QLabel('')
        self._boot_count_label.setFont(QFont('IBM Plex Mono', 11))
        self._boot_count_label.setStyleSheet(
            "color: rgba(255,255,255,36); background: transparent;"
        )
        self._boot_count_label.setAlignment(Qt.AlignCenter)

        profile_tag = ' · sim' if _sim_mode.is_active() else ''
        ver_lbl = QLabel(f'v{_APP_VERSION} · {_HOSTNAME} · {_LOCAL_IP}{profile_tag}')
        ver_lbl.setFont(QFont('IBM Plex Mono', 12))
        ver_lbl.setStyleSheet("color: rgba(255,255,255,46); background: transparent;")

        footer.addWidget(org_lbl)
        footer.addStretch()
        footer.addWidget(self._boot_count_label)
        footer.addStretch()
        footer.addWidget(ver_lbl)
        root.addLayout(footer)

    def _make_cam_card(self, cam_idx: int, cam_label: str, name: str,
                       subtitle: str, ip: str, status: str) -> QFrame:
        card = QFrame()
        card.setObjectName("cam_card")
        card.setFrameShape(QFrame.NoFrame)
        card.setFrameShadow(QFrame.Plain)
        card.setLineWidth(0)
        card.setMidLineWidth(0)
        card.setFixedSize(300, 170)
        self._style_card(card, status)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(0)

        # ── Encabezado: etiqueta de cámara (izq) + LED (der) ──────────────
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(0)
        mode_lbl = QLabel(cam_label.upper())
        mode_lbl.setFont(QFont('Inter Tight', 11, QFont.Bold))
        mode_lbl.setStyleSheet(
            "color: rgba(255,255,255,89); background: transparent; letter-spacing: 3px;"
        )
        led = QLabel()
        led.setFixedSize(14, 14)
        self._style_led(led, status)
        header.addWidget(mode_lbl)
        header.addStretch()
        header.addWidget(led)
        layout.addLayout(header)
        layout.addSpacing(10)

        # ── Nombre + subtítulo ─────────────────────────────────────────────
        name_lbl = QLabel(name)
        name_lbl.setFont(QFont('Inter Tight', 20, QFont.Bold))
        name_lbl.setStyleSheet("color: rgba(255,255,255,217); background: transparent;")
        layout.addWidget(name_lbl)

        sub_lbl = QLabel(subtitle)
        sub_lbl.setFont(QFont('Inter Tight', 12))
        sub_lbl.setStyleSheet("color: rgba(255,255,255,89); background: transparent;")
        layout.addWidget(sub_lbl)
        layout.addSpacing(8)

        # ── IP ────────────────────────────────────────────────────────────
        ip_lbl = QLabel(str(ip) if ip else '---')
        ip_lbl.setFont(QFont('IBM Plex Mono', 11))
        ip_lbl.setStyleSheet(
            "color: rgba(255,255,255,64);"
            "background: rgba(255,255,255,13);"
            "padding: 3px 8px;"
            "border-radius: 6px;"
        )
        layout.addWidget(ip_lbl)
        layout.addSpacing(8)

        # ── Fila de estado ─────────────────────────────────────────────────
        status_lbl = QLabel(self._CAM_STATE[status]['label'])
        status_lbl.setFont(QFont('Inter Tight', 13, QFont.Medium))
        self._style_status_text(status_lbl, status)
        layout.addWidget(status_lbl)

        # Guardar referencias
        if cam_idx == 1:
            self._cam1_led        = led
            self._cam1_status_lbl = status_lbl
            self._cam1_card_ref   = card
        else:
            self._cam2_led        = led
            self._cam2_status_lbl = status_lbl
            self._cam2_card_ref   = card

        return card

    def _make_chip(self, name: str) -> QLabel:
        """Pill badge para el estado de un fichero de datos.
        ● verde = ok, ● rojo = error/ausente, ● gris = cargando.
        """
        chip = QLabel(f'● {name}')
        chip.setFont(QFont('Inter Tight', 12))
        chip.setStyleSheet(
            "color: rgba(255,255,255,0.28);"
            "background: rgba(255,255,255,0.05);"
            "padding: 4px 12px;"
            "border-radius: 12px;"
            "border: 1px solid rgba(255,255,255,0.07);"
        )
        return chip

    # ── Helpers de estilo ─────────────────────────────────────────────────

    def _style_card(self, card: QFrame, status: str):
        st = self._CAM_STATE.get(status, self._CAM_STATE['connecting'])
        name = card.objectName()
        card.setStyleSheet(
            f"QFrame#{name} {{"
            f"  background: {st['bg']};"
            f"  border: 1px solid {st['border']};"
            f"  border-radius: 16px;"
            f"}}"
        )

    def _style_led(self, led: QLabel, status: str, dimmed: bool = False):
        st = self._CAM_STATE.get(status, self._CAM_STATE['connecting'])
        color = st['led']
        r, g, b = st['glow']
        led.setStyleSheet(
            f"QLabel {{"
            f"  background: {color};"
            f"  border-radius: 7px;"
            f"}}"
        )
        effect = QGraphicsDropShadowEffect(led)
        effect.setOffset(0, 0)
        if dimmed:
            effect.setBlurRadius(6)
            effect.setColor(QColor(r, g, b, 80))
        else:
            effect.setBlurRadius(12)
            effect.setColor(QColor(r, g, b, 160))
        led.setGraphicsEffect(effect)

    def _style_status_text(self, lbl: QLabel, status: str):
        st = self._CAM_STATE.get(status, self._CAM_STATE['connecting'])
        lbl.setStyleSheet(f"color: {st['text']}; background: transparent;")

    # ── Reloj en vivo ─────────────────────────────────────────────────────

    def _tick_clock(self):
        now = datetime.now()
        self._clock_label.setText(now.strftime('%H:%M:%S'))
        self._date_label.setText(now.strftime('%a %d %b %Y'))

    # ── Panel de horario de hoy ───────────────────────────────────────────

    def _apply_schedule_display(self):
        """Lee schedule.json síncronamente y actualiza el label de horario.

        Seguro llamar desde el hilo principal (main thread). Usado tanto en
        _build_ui (visualización inmediata) como desde el slot _do_schedule_text
        (confirmación tras validación en background). Nunca lanza excepciones.
        """
        try:
            schedule = load_schedule()
            if schedule.get('always_bypass', False):
                self._schedule_label.setText('Access schedule: always open')
                self._schedule_label.setStyleSheet(
                    "color: rgba(255,255,255,0.35); background: transparent;"
                )
                return

            now = datetime.now()
            today_name = _SCHED_DAYS[now.weekday()]
            entry = schedule.get(today_name, {})
            if entry.get('enabled', False):
                start = entry.get('start', '??:??')
                end   = entry.get('end', '??:??')
                # Comprobar si la ventana está activa ahora mismo
                active = self._is_entry_active_now(entry)
                if active:
                    self._schedule_label.setText(
                        f'Session window active now:  {start} – {end}'
                    )
                    self._schedule_label.setStyleSheet(
                        "color: rgba(35,170,70,0.90); background: transparent;"
                    )
                else:
                    self._schedule_label.setText(
                        f'Session window today:  {start} – {end}'
                    )
                    self._schedule_label.setStyleSheet(
                        "color: rgba(35,170,70,0.58); background: transparent;"
                    )
            else:
                self._schedule_label.setText(
                    f'No session scheduled for {self._DAY_NAMES[now.weekday()]}'
                )
                self._schedule_label.setStyleSheet(
                    "color: rgba(255,255,255,0.28); background: transparent;"
                )
        except Exception as exc:
            logger.warning("Schedule display error: %s", exc)
            self._schedule_label.setText('Schedule unavailable')
            self._schedule_label.setStyleSheet(
                "color: rgba(255,255,255,0.28); background: transparent;"
            )

    @staticmethod
    def _is_entry_active_now(entry: dict) -> bool:
        """True si la hora actual cae dentro del intervalo de *entry*."""
        try:
            sh, sm = map(int, entry.get('start', '').split(':'))
            eh, em = map(int, entry.get('end', '').split(':'))
        except (ValueError, AttributeError):
            return False
        now = datetime.now()
        cur = now.hour * 60 + now.minute
        start = sh * 60 + sm
        end   = eh * 60 + em
        if end <= start:          # ventana nocturna (p.ej. 22:00 → 06:00)
            return cur >= start or cur < end
        return start <= cur < end

    # ── Pulso LED ─────────────────────────────────────────────────────────

    def _pulse_leds(self):
        self._led_pulse_on = not self._led_pulse_on
        for cam_idx in (1, 2):
            status = self._cam1_status if cam_idx == 1 else self._cam2_status
            if status == 'connecting':
                led = self._cam1_led if cam_idx == 1 else self._cam2_led
                self._style_led(led, 'connecting', dimmed=not self._led_pulse_on)

    # ─────────────────────────────────────────────────────────────────────────
    #  Slots de UI (siempre en hilo principal)
    # ─────────────────────────────────────────────────────────────────────────

    def _do_log(self, message: str):
        """Actualizar log — llamado sólo desde el hilo principal vía señal."""
        current = self.log_label.text()
        lines = (current + message + "\n").split('\n')
        # Mantener solo las últimas 20 líneas para no desbordar el label
        if len(lines) > 20:
            lines = lines[-20:]
        self.log_label.setText('\n'.join(lines))

    def _do_status(self, message: str, color: str):
        """Actualizar etiqueta de estado — llamado sólo desde el hilo principal."""
        colors = {"green": "rgba(35,170,70,0.7)", "yellow": "#F5A623", "red": "rgba(190,35,35,0.7)"}
        self.subtitle_label.setText(message)
        self.subtitle_label.setStyleSheet(
            f"color: {colors.get(color, 'rgba(255,255,255,102)')}; background: transparent;"
        )

    def _do_cam_update(self, cam_idx: int, status: str):
        """Actualizar tarjeta de cámara — llamado sólo desde el hilo principal."""
        if cam_idx == 1:
            self._cam1_status = status
            card = self._cam1_card_ref
            led  = self._cam1_led
            lbl  = self._cam1_status_lbl
        else:
            self._cam2_status = status
            card = self._cam2_card_ref
            led  = self._cam2_led
            lbl  = self._cam2_status_lbl

        self._style_card(card, status)
        self._style_led(led, status)
        self._style_status_text(lbl, status)
        lbl.setText(self._CAM_STATE.get(status, self._CAM_STATE['connecting'])['label'])

    def _do_ticker(self, name: str, success: bool):
        """Añadir resultado al ticker rodante."""
        self.ticker_widget.add_result(name, success)

    def _do_show_interrupted(self, timestamp: str):
        """Mostrar el banner de sesión interrumpida con el timestamp."""
        started_at = timestamp.strip() if timestamp else ''
        if started_at:
            try:
                dt = datetime.fromisoformat(started_at)
                started_at = dt.strftime('%H:%M on %a %d %b')
            except ValueError:
                pass
            self._interrupted_lbl.setText(
                f'Previous session interrupted at {started_at} — check cameras before starting'
            )
        self._interrupted_banner.setVisible(True)

    def _do_chip_update(self, chip_name: str, ok: bool):
        """Actualizar pill badge con el estado del fichero."""
        chip = self._chip_labels.get(chip_name)
        if chip is None:
            return
        if ok:
            color  = 'rgba(35,170,70,0.80)'
            bg     = 'rgba(35,170,70,0.10)'
            border = '1px solid rgba(35,170,70,0.25)'
        else:
            color  = 'rgba(190,35,35,0.80)'
            bg     = 'rgba(190,35,35,0.08)'
            border = '1px solid rgba(190,35,35,0.22)'
        chip.setStyleSheet(
            f"color: {color};"
            f"background: {bg};"
            f"border: {border};"
            "padding: 4px 14px 4px 10px;"
            "border-radius: 12px;"
        )

    def _do_schedule_text(self, text: str, color_key: str):
        """Confirmación del horario desde phase 1 (background thread → main thread).
        Re-aplica la visualización completa (incluye "active now") en vez de
        sobreescribir con texto plano, para coherencia con _apply_schedule_display.
        """
        # text y color_key son ignorados: releer el archivo asegura coherencia
        # y aplica el indicador "active now" con lógica canónica.
        self._apply_schedule_display()

    def _do_boot_footer(self, text: str):
        """Actualizar contador de boots en el footer."""
        self._boot_count_label.setText(text)

    # ─────────────────────────────────────────────────────────────────────────
    #  API pública para hilos de fondo (emiten señales, nunca tocan widgets)
    # ─────────────────────────────────────────────────────────────────────────

    def _update_log(self, message: str):
        self._sig_log.emit(message)

    def _update_status(self, message: str, color: str = "white"):
        self._sig_status.emit(message, color)

    def _update_progress(self, value: int):
        self._sig_progress.emit(value)

    # ─────────────────────────────────────────────────────────────────────────
    #  Teclado
    # ─────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            self.diagnostic_mode = True
            self._update_log("DIAGNOSTIC MODE ACTIVATED")
        super().keyPressEvent(event)

    # ─────────────────────────────────────────────────────────────────────────
    #  INICIALIZACIÓN (hilo de fondo)
    # ─────────────────────────────────────────────────────────────────────────

    def _start_initialization(self):
        if self.__dict__.get('_init_started', False):
            return
        self.__dict__['_init_started'] = True
        threading.Thread(target=self._startup_sequence, daemon=True).start()

    def _startup_sequence(self):
        """Three-phase startup: config/data → hardware → tests.

        Phase 1 validates config and data files before any hardware is touched.
        Phase 2 powers on cameras with a bounded timeout; times out gracefully.
        Phase 3 runs all diagnostic tests in parallel and emits startup_complete.
        """
        # ── Phase 1: Config and data ──────────────────────────────────────────
        logger.info("[STARTUP][PHASE 1] Config and data validation starting")
        phase1_ok = self._run_config_phase()
        if phase1_ok:
            logger.info("[STARTUP][PHASE 1] Config and data OK")
        else:
            logger.warning("[STARTUP][PHASE 1] Config or data issues detected — hardware phase will still run")

        # ── Phase 2: Hardware (camera power-on) ──────────────────────────────
        logger.info("[STARTUP][PHASE 2] Hardware startup starting")
        cam_thread = threading.Thread(target=self._startup_cameras, daemon=True)
        cam_thread.start()
        cam_thread.join(timeout=CAMERA_STARTUP_TIMEOUT_SECONDS)
        if cam_thread.is_alive():
            from domain.startup_errors import recoverable
            err = recoverable("camera", f"startup did not complete within {CAMERA_STARTUP_TIMEOUT_SECONDS}s")
            logger.warning("[STARTUP][PHASE 2][%s] %s — continuing in degraded mode", err.kind.value, err)
            self._update_log("Camera startup incomplete. Continuing in degraded mode.")
            self._update_status("Camera startup timeout — degraded mode", "yellow")
        else:
            logger.info("[STARTUP][PHASE 2] Hardware startup complete")

        # ── Phase 3: Diagnostic tests ─────────────────────────────────────────
        logger.info("[STARTUP][PHASE 3] Diagnostic tests starting")
        self._run_initialization()

    def _run_config_phase(self) -> bool:
        """Phase 1: validate config values and runtime data files before hardware starts.

        Returns True if all checks pass, False if any issue was detected.
        Logs each check with [PHASE 1] prefix. Never raises.
        """
        ok = True

        # Config values (IPs, IDs, seat positions)
        try:
            config_ok = all([CAM1.ip, CAM1.cam_id, CAM2.ip, CAM2.cam_id, SEAT_POSITIONS])
            if config_ok:
                logger.info("[STARTUP][PHASE 1] Camera config: OK")
            else:
                logger.warning("[STARTUP][PHASE 1] Camera config: missing values — check PTZxIP.txt and CamxID.txt")
                ok = False
        except Exception as exc:
            logger.warning("[STARTUP][PHASE 1] Camera config: error reading config — %s", exc)
            ok = False

        # Runtime data files — validate and update chips
        from config import NAMES_FILE
        for label, path, chip_name in [
            ("schedule.json", _RuntimePathResolver().schedule_file, "schedule"),
            ("seat_names.json", NAMES_FILE, "seat names"),
        ]:
            try:
                if path.exists():
                    json.loads(path.read_text(encoding="utf-8"))
                    logger.info("[STARTUP][PHASE 1] %s: OK", label)
                    self._sig_chip_update.emit(chip_name, True)
                else:
                    logger.info("[STARTUP][PHASE 1] %s: not present — defaults will be used", label)
                    self._sig_chip_update.emit(chip_name, False)
            except Exception as exc:
                logger.warning("[STARTUP][PHASE 1] %s: unreadable — %s", label, exc)
                self._sig_chip_update.emit(chip_name, False)
                ok = False

        # Presets chip
        presets_path = _RuntimePathResolver().chairman_presets_file
        presets_ok = presets_path.exists()
        self._sig_chip_update.emit("presets", presets_ok)
        if not presets_ok:
            logger.info("[STARTUP][PHASE 1] chairman_presets.json: not present — no presets saved yet")

        # Horario de hoy
        self._emit_schedule_info()

        # Leftover temp/corrupt file detection (#166)
        from core.json_io import detect_leftover_files
        for suspicious in detect_leftover_files(_RuntimePathResolver().data_dir):
            logger.warning(
                "[STARTUP][PHASE 1] Leftover file detected: %s — "
                "may indicate a previous interrupted write. Do not delete without diagnosis.",
                suspicious.name,
            )
            ok = False

        # Interrupted session detection (#120)
        from application.session_marker import was_session_interrupted
        marker_file = _RuntimePathResolver().session_marker_file
        if was_session_interrupted():
            ok = False
            try:
                timestamp = marker_file.read_text(encoding="utf-8").strip()
            except OSError:
                timestamp = ""
            self._sig_interrupted.emit(timestamp)

        return ok

    def _emit_schedule_info(self):
        """Emite señal para que el hilo principal refresque el panel de horario.
        El slot (_do_schedule_text) llama a _apply_schedule_display, que
        contiene toda la lógica. Los argumentos son ignorados.
        """
        self._sig_schedule_text.emit('', '')

    def _startup_cameras(self):
        """Power on cameras only if in standby; skip Home if already on to avoid mid-session disruption."""
        cam1_was_on = self._query_camera_powered(CAM1.ip, CAM1.cam_id)
        cam2_was_on = self._query_camera_powered(CAM2.ip, CAM2.cam_id)

        if cam1_was_on:
            logger.info("Camera startup: CAM1 (%s) already powered — skipping Power ON and Home", CAM1.ip)
        else:
            logger.info("Camera startup: sending Power ON to CAM1 (%s)", CAM1.ip)
            self._power_on_camera(CAM1.ip, CAM1.cam_id)

        if cam2_was_on:
            logger.info("Camera startup: CAM2 (%s) already powered — skipping Power ON and Home", CAM2.ip)
        else:
            logger.info("Camera startup: sending Power ON to CAM2 (%s)", CAM2.ip)
            self._power_on_camera(CAM2.ip, CAM2.cam_id)

        if cam1_was_on and cam2_was_on:
            logger.info("Camera startup: complete (both cameras were already on)")
            return

        # Only wait and send Home for cameras we actually powered on
        time.sleep(8)
        if not cam1_was_on:
            logger.info("Camera startup: sending Home to CAM1 (%s)", CAM1.ip)
            self._home_camera(CAM1.ip, CAM1.cam_id)
        if not cam2_was_on:
            logger.info("Camera startup: sending Home to CAM2 (%s)", CAM2.ip)
            self._home_camera(CAM2.ip, CAM2.cam_id)
        logger.info("Camera startup: complete")

    def _run_initialization(self):
        """
        Ejecuta todos los tests en paralelo.
        Siempre emite startup_complete al finalizar (con o sin errores).
        """
        tests = [
            ("Operating System",       self._test_os),
            ("Network Connectivity",   self._test_network),
            ("Camera 1 (Platform)",    self._test_camera1),
            ("Camera 2 (Audience)",    self._test_camera2),
            ("Configuration",          self._test_config),
            ("Statistics",             self._test_statistics),
            ("Focus & Exposure Cam1",  self._test_focus_exposure_cam1),
            ("Focus & Exposure Cam2",  self._test_focus_exposure_cam2),
            ("Data Files",             self._test_data_files),
            ("TCP Scan (cameras)",     self._test_tcp_scan),
            ("ARP Table",              self._test_arp_table),
        ]
        self.tests_total = len(tests)

        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {
                    executor.submit(self._run_single_test, name, func): name
                    for name, func in tests
                }
                for future in as_completed(futures):
                    test_name = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"success": False, "error": str(exc), "duration_ms": 0}
                    self._process_test_result(test_name, result)

            # Estadísticas de boot
            duration_ms = int((time.time() - self.boot_start_time) * 1000)
            self.boot_stats.record_boot(duration_ms, self.tests_passed, self.tests_total)

            summary = self.boot_stats.get_summary()
            if summary:
                boot_text = f"boot #{summary['total_boots']} · {summary['success_rate']} ok"
                self._sig_boot_footer.emit(boot_text)

            # Estado final
            if self.tests_passed == self.tests_total:
                self._update_log("\nAll tests passed")
                self._update_status(f"Ready ({self.tests_passed}/{self.tests_total})", "green")
            else:
                self._update_status(
                    f"{self.tests_passed}/{self.tests_total} tests passed — continuing",
                    "yellow"
                )
                self._update_log(f"\n{self.tests_passed}/{self.tests_total} passed. Continuing...")

            time.sleep(3 if _sim_mode.is_active() else 1)

        except Exception as exc:
            self._update_log(f"\nWarning during initialization: {exc}")
            self._update_status("Starting with warnings...", "yellow")
            time.sleep(3 if _sim_mode.is_active() else 1)

        finally:
            # Siempre continuar: las cámaras no son requisito para arrancar
            self.startup_complete.emit()

    def _run_single_test(self, name: str, test_func) -> dict:
        """
        Ejecuta un test con hasta 3 reintentos (backoff exponencial).
        Solo reintenta si lanza excepción; False se acepta como resultado.
        En modo simulación añade un retardo por test para que el ticker
        sea legible y el splash no desaparezca de inmediato.
        """
        result = TestResult(name)
        max_retries = 3
        backoff_ms  = 100

        for attempt in range(1, max_retries + 1):
            try:
                success = test_func()
                result.finish(success)
                if _sim_mode.is_active():
                    time.sleep(0.45)
                return result.to_dict()
            except Exception as exc:
                if attempt < max_retries:
                    wait = backoff_ms * (2 ** (attempt - 1)) / 1000
                    self._update_log(f"  retry {name} ({int(wait*1000)}ms)...")
                    time.sleep(wait)
                else:
                    result.finish(False, str(exc))
                    if _sim_mode.is_active():
                        time.sleep(0.45)
                    return result.to_dict()

    # Nombres cortos para el ticker
    _TICKER_SHORT: ClassVar[dict] = {
        "Operating System":      "OS",
        "Network Connectivity":  "Net",
        "Camera 1 (Platform)":   "Cam1",
        "Camera 2 (Audience)":   "Cam2",
        "Configuration":         "Config",
        "Statistics":            "Stats",
        "Focus & Exposure Cam1": "Focus1",
        "Focus & Exposure Cam2": "Focus2",
        "Data Files":            "Files",
        "TCP Scan (cameras)":    "TCP",
        "ARP Table":             "ARP",
    }

    def _process_test_result(self, test_name: str, result: dict):
        """Procesar resultado de un test completado."""
        self.test_results[test_name] = result

        if result.get("success"):
            self._update_log(f"  OK  {test_name} ({result.get('duration_ms', 0)}ms)")
            self.tests_passed += 1
        else:
            error = result.get("error") or ""
            suffix = f" — {error}" if error else ""
            self._update_log(f"  --  {test_name}{suffix}")

        # Ticker
        short = self._TICKER_SHORT.get(test_name, test_name[:6])
        self._sig_ticker.emit(short, bool(result.get("success")))

        # Actualizar tarjetas de cámara
        device_status = 'connected' if result.get('success') else 'disconnected'
        if 'Camera 1' in test_name:
            self._sig_cam_update.emit(1, device_status)
        elif 'Camera 2' in test_name:
            self._sig_cam_update.emit(2, device_status)
        progress = int(len(self.test_results) / self.tests_total * 100)
        self._update_progress(progress)

    # ─────────────────────────────────────────────────────────────────────────
    #  TESTS
    # ─────────────────────────────────────────────────────────────────────────

    def _send_visca_cmd(self, ip: str, cam_id: str, cmd: str) -> bool:
        """Envía un comando VISCA y devuelve True si la cámara responde."""
        try:
            full_cmd = cam_id + cmd
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect((ip, VISCA_PORT))
                sock.send(binascii.unhexlify(full_cmd))
                data = sock.recv(64)
                return len(data) > 0
        except Exception:
            return False

    def _test_focus_exposure_cam1(self) -> bool:
        """
        Verifica que los comandos de foco y exposición llegan correctamente a Cam1.
        Envía Auto Focus, Brightness Up y Backlight ON.
        En modo simulación devuelve True directamente (sin hardware real).
        """
        if _sim_mode.is_active():
            return True
        af_ok = self._send_visca_cmd(CAM1.ip, CAM1.cam_id, "01043802FF")  # Auto Focus
        br_ok = self._send_visca_cmd(CAM1.ip, CAM1.cam_id, "01040D02FF")  # Brightness Up
        bl_ok = self._send_visca_cmd(CAM1.ip, CAM1.cam_id, "01043302FF")  # Backlight ON
        return af_ok and br_ok and bl_ok

    def _test_focus_exposure_cam2(self) -> bool:
        """
        Verifica que los comandos de foco y exposición llegan correctamente a Cam2.
        Envía Auto Focus y Brightness Up.
        En modo simulación devuelve True directamente (sin hardware real).
        """
        if _sim_mode.is_active():
            return True
        af_ok = self._send_visca_cmd(CAM2.ip, CAM2.cam_id, "01043802FF")  # Auto Focus
        br_ok = self._send_visca_cmd(CAM2.ip, CAM2.cam_id, "01040D02FF")  # Brightness Up
        return af_ok and br_ok

    def _test_data_files(self) -> bool:
        """Verifica que seat_names.json y schedule.json son legibles y JSON válido."""
        from config import NAMES_FILE
        names_ok = True
        try:
            if NAMES_FILE.exists():
                json.loads(NAMES_FILE.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            names_ok = False

        sched_ok = True
        try:
            _sched_file = _RuntimePathResolver().schedule_file
            if _sched_file.exists():
                json.loads(_sched_file.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            sched_ok = False

        return names_ok and sched_ok

    def _test_os(self) -> bool:
        import platform
        return bool(platform.system())

    def _test_network(self) -> bool:
        socket.gethostbyname('localhost')
        return True

    def _test_camera1(self) -> bool:
        return self._test_camera(CAM1.ip, CAM1.cam_id)

    def _test_camera2(self) -> bool:
        return self._test_camera(CAM2.ip, CAM2.cam_id)

    def _test_camera(self, ip: str, cam_id: str) -> bool:
        """
        Prueba conexión TCP con una cámara y la enciende si responde.
        Usa context manager para garantizar que el socket se cierra aunque
        connect_ex lance OSError (evita leak de file descriptors).
        En modo simulación devuelve True directamente (sin hardware real).
        """
        if _sim_mode.is_active():
            return True
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                connected = sock.connect_ex((ip, VISCA_PORT)) == 0
        except OSError:
            return False

        if connected:
            self._power_on_camera(ip, cam_id)
        return connected

    def _test_config(self) -> bool:
        return all([CAM1.ip, CAM1.cam_id, CAM2.ip, CAM2.cam_id, SEAT_POSITIONS])

    def _test_statistics(self) -> bool:
        return self.boot_stats.stats_file.exists()

    # ─────────────────────────────────────────────────────────────────────────
    #  HELPERS DE CÁMARA
    # ─────────────────────────────────────────────────────────────────────────

    def _query_camera_powered(self, ip: str, cam_id: str) -> bool:
        """Returns True if the camera reports power ON (0x02). Returns False on any error or standby (0x03)."""
        try:
            cmd = binascii.unhexlify(cam_id + "090400FF")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect((ip, VISCA_PORT))
                sock.send(cmd)
                resp = sock.recv(64)
            # y0 50 02 FF = ON,  y0 50 03 FF = STANDBY
            return len(resp) >= 3 and resp[1] == 0x50 and resp[2] == 0x02
        except Exception:
            return False

    def _power_on_camera(self, ip: str, cam_id: str):
        """Envía comando VISCA Power On. Falla silenciosamente."""
        try:
            cmd = cam_id + "01040002FF"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect((ip, VISCA_PORT))
                sock.send(binascii.unhexlify(cmd))
                sock.recv(64)
        except Exception:
            pass

    def _home_camera(self, ip: str, cam_id: str):
        """Envía comando VISCA Home. Falla silenciosamente."""
        try:
            cmd = cam_id + "010604FF"
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(SOCKET_TIMEOUT)
                sock.connect((ip, VISCA_PORT))
                sock.send(binascii.unhexlify(cmd))
                sock.recv(64)
        except Exception:
            pass

    # ─────────────────────────────────────────────────────────────────────────
    #  DESCUBRIMIENTO DE CÁMARAS  (lógica en camera_discovery.py)
    # ─────────────────────────────────────────────────────────────────────────

    def _test_tcp_scan(self) -> bool:
        """
        Escanea toda la subred /24 de las cámaras en VISCA_PORT con 50 workers
        paralelos y registra los hosts que responden.
        Delega en camera_discovery.tcp_scan().
        En modo simulación devuelve True directamente (sin hardware real).
        """
        if _sim_mode.is_active():
            self._update_log("  TCP scan: simulation mode — skipped")
            return True
        subnet = get_camera_subnet()
        self._update_log(f"  Scanning {subnet}.1-254 port {VISCA_PORT}...")
        found = tcp_scan(subnet)
        if found:
            self._update_log(f"  VISCA found: {', '.join(found)}")
        else:
            self._update_log(f"  No VISCA devices on {subnet}.x")
        return bool(found)

    def _test_arp_table(self) -> bool:
        """
        Lee la tabla ARP del sistema y registra las entradas que pertenecen
        a la subred de las cámaras.
        Delega en camera_discovery.arp_scan().
        En modo simulación devuelve True directamente (sin hardware real).
        """
        if _sim_mode.is_active():
            self._update_log("  ARP scan: simulation mode — skipped")
            return True
        subnet = get_camera_subnet()
        unique = arp_scan(subnet)
        if unique:
            self._update_log(f"  ARP ({subnet}.x): {', '.join(unique)}")
        else:
            self._update_log(f"  ARP: no entries for {subnet}.x")
        return bool(unique)
