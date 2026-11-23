#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# main_window.py — Ventana principal: layout de UI + wire-up de AsyncEventBus
#
# ARQUITECTURA:
#   MainWindow solo hace:
#     1. Construir widgets y layout
#     2. Instanciar las capas (SystemState, AsyncEventBus, servicios, Controller)
#     3. Conectar señales Qt → AsyncEventBus.emit()
#     4. Suscribirse a eventos del bus para actualizar display
#
#   Nunca llama a VISCA directamente.
#   Nunca llama a CameraManager directamente (excepto para workers de señales Qt).
#
# CAMBIOS RESPECTO A VERSIÓN ANTERIOR:
#   - Eliminados _chairman_recall() y _save_chairman_preset(): Controller los gestiona.
#   - ChairmanButton recibe bus + preset_svc en lugar de callbacks y presets_ref.
#   - SessionController se actualiza para usar SessionService vía Controller.
#   - AsyncEventBus conecta joystick, asientos, chairman → Controller → CameraPort.

from __future__ import annotations

import logging
import os
import time
import weakref
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from domain.shutdown_intent import ShutdownIntent

from PyQt5 import QtGui, QtCore, sip
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QButtonGroup, QLabel, QMainWindow,
    QMessageBox, QPushButton,
)

logger = logging.getLogger(__name__)

from config import (
    CAM1, CAM2,
    ATEM,
    load_names_data,
    PAN_SPEED_MAX,
    TILT_SPEED_MAX,
    ZOOM_DRIVE_MAX,
)
from domain.atem_state import ATEMState, is_atem_supervisor_healthy
from domain.adaptive_speed import zoom_to_raw_speed, fresh_channel_state
from adapters.atem_monitor import ATEMMonitor
from adapters.atem_dispatcher import ATEMDispatcher
from ptz.visca import CameraManager
from ui.widgets import GoButton, SpecialDragButton, PlatformPresetButton
from ui.names_panel import NamesPanel
from ui.atem_operational import AtemOperationalMixin
from ui.camera_display_mixin import CameraDisplayMixin
from ui.session_mixin import SessionController
from ui.dialogs_mixin import DialogsController
from ui.config_dialog import ConfigDialog
from ui.seat_names_mixin import SeatNamesController
from ui.seat_registry import SeatRegistry, seat_button

from ui.platform_icons import SVG_LEFT, SVG_CHAIRMAN, SVG_RIGHT
from ui.seat_builder import build_special_seat_button

from ui.chairman_button import ChairmanButton
from ui.camera_indicator import CameraIndicator
from ui.auditorium_overlay import AuditoriumOverlay
from ui.mode_border_overlay import ModeBorderOverlay

# ── Arquitectura: AppContext y bootstrap ──────────────────────────────────────
from core.events import EventType
from bootstrap import build_app_context
from domain.preset import PRESET_CHAIRMAN_GENERIC, PLATFORM_PRESETS, PRESET_PLATFORM_2
from application.call_set_command_policy import CallSetCommandPolicy
from application.access_mode_service import AccessModeService
from domain.call_set_policy import InputType, OperatingMode
from adapters.screen_monitor import ScreenMonitor
from ui.screen_off_dialog import ScreenOffDialog
from adapters.gpio_monitor import GpioMonitor


def _load_cam_configs_from_yaml():
    """Load camera and ATEM config objects from config.yaml.

    Returns (cam1, cam2) with real IPs from config.yaml when available.
    Falls back to the CAM1/CAM2 globals (empty-string defaults, or sim-patched)
    when config.yaml is absent or unreadable. Also hydrates the ATEM global
    from the same effective settings: it is the monitor's only boot-time
    source for the switcher IP.
    """
    import adapters.sim_mode as sim_mode
    if sim_mode.is_active():
        return CAM1, CAM2
    try:
        from config.effective import load_effective_config as load_config
        from runtime.path_resolver import RuntimePathResolver
        settings = load_config(RuntimePathResolver().config_dir / "config.yaml")
        from ui.camera_config_hydration import hydrate_atem, hydrate_camera_roles
        hydrate_camera_roles(settings.cameras, CAM1, CAM2)
        hydrate_atem(getattr(settings, 'atem', None), ATEM)
        return CAM1, CAM2
    except Exception:
        return CAM1, CAM2


def _load_second_platform_enabled() -> bool:
    """Read the operator's Platform 2 preference from the runtime data dir.

    Works in every profile (production, demo, simulation). Returns False on any
    error or when the preference has never been set.
    """
    try:
        from application.display_prefs import is_second_platform_enabled
        return is_second_platform_enabled()
    except Exception:
        return False


class MainWindow(QMainWindow, CameraDisplayMixin, AtemOperationalMixin):
    """Ventana principal 1920x1080 px."""

    atem_state_changed = pyqtSignal(object)

    _WATCHDOG_COOLDOWN       = 1.5     # s mínimos entre dos reducciones del mismo tipo
    _WATCHDOG_RECOVERY_MS    = 20_000  # ms hasta el primer intento de recuperación
    _WATCHDOG_WINDOW_SECS    = 300     # ventana de 5 min: más de 3 fallos → bloqueado
    _WATCHDOG_MAX_RETRIES    = 3       # intentos de recuperación antes de bloquear

    def __init__(self):
        super().__init__()

        self.setWindowTitle('Camera Controls')
        self.setGeometry(0, 0, 1920, 1080)

        self.session_active  = False
        self._seat_pending: Optional[int] = None
        self._seat_pending_camera: Optional[int] = None
        self._last_activity: float = time.monotonic()
        self._pan_cap:        int = PAN_SPEED_MAX   # 24 — watchdog lo reduce en error move
        self._tilt_cap:       int = TILT_SPEED_MAX  # 20 — watchdog lo reduce en error move
        self._zoom_drive_cap: int = ZOOM_DRIVE_MAX  # 7  — watchdog lo reduce en error zoom_drive
        self._watchdog_state: dict = {
            'move':       self._fresh_watchdog_state(),
            'zoom_drive': self._fresh_watchdog_state(),
        }
        # In simulation mode, patch CAM1/CAM2 IPs before any worker is created.
        # This must happen before _load_cam_configs_from_yaml() so the fallback
        # path returns the sim IPs when config.yaml is absent.
        # Single owner of camera/ATEM config writes (ADR-006). Widgets call this
        # instead of assigning config.CAMn.* directly; providers resolve the live
        # runtime lazily because _cameras/_camera_port are built just below.
        from application.camera_config_service import CameraConfigService
        from ui.config_edit_dialogs import _config_yaml_path
        self._camera_config = CameraConfigService(
            config_path_provider=_config_yaml_path,
            camera_manager_provider=lambda: getattr(self, "_cameras", None),
            camera_port_provider=lambda: getattr(self, "_camera_port", None),
        )

        import adapters.sim_mode as _sim_mode_init
        if _sim_mode_init.is_active():
            self._camera_config.apply_simulation_ips(
                _sim_mode_init.SIM_VALUES.get("PTZ1IP.txt", "127.0.0.1"),
                _sim_mode_init.SIM_VALUES.get("PTZ2IP.txt", "127.0.0.2"),
            )

        _cam1_cfg, _cam2_cfg = _load_cam_configs_from_yaml()
        self._cameras = CameraManager(_cam1_cfg, _cam2_cfg, on_worker_ready=self._on_worker_ready)

        _data = load_names_data()
        self._names_list = _data["names"]
        self._seat_names = _data["seats"]

        # ── Nueva arquitectura: construir contexto vía bootstrap ──────────
        _ctx = build_app_context(self._cameras)
        self._state                 = _ctx.state
        self._bus                   = _ctx.bus
        self._preset_svc            = _ctx.preset_svc
        self._camera_port           = _ctx.camera_port
        self._session_svc           = _ctx.session_svc
        self._controller            = _ctx.controller
        self._app_ctrl              = _ctx.app_ctrl
        self._camera_target_resolver = _ctx.camera_target_resolver
        self._layout_svc            = _ctx.layout_svc
        self._runtime_safety_svc    = _ctx.runtime_safety_svc

        self._session         = SessionController(self)
        self._dialogs         = DialogsController(self)
        self._seat_names_ctrl = SeatNamesController(self)
        self._call_set_policy = CallSetCommandPolicy()
        self._access_mode_svc = AccessModeService()

        self._build_ui()
        self._build_overlays()
        self._bus.subscribe_qt(EventType.CAMERA_ZOOM_INVALIDATED, self._on_zoom_invalidated)

        # Crear los workers iniciales (arranca su thread TCP). El cableado de
        # las señales de estado de conexión a los LEDs vive en _on_worker_ready,
        # que también corre para los workers RECREADOS cuando el operador cambia
        # la IP en Ajustes. Antes el LED sólo se cableaba a los workers de
        # arranque, así que tras cambiar la IP la cámara reconectaba pero el LED
        # se quedaba en rojo / "desconectado".
        from ui.camera_worker_startup import start_configured_camera_workers
        start_configured_camera_workers(self._cameras)
        self._update_controls_visibility()

        # ── Modo simulación ───────────────────────────────────────────────
        if _sim_mode_init.is_active():
            from simulation.sim_worker import start_simulation
            start_simulation(CAM1.ip, CAM2.ip)

        self._atem_state: ATEMState = ATEMState.NOT_CONFIGURED
        self._atem_restart_pending = False
        # Marca temporal del DISCONNECTED terminal actual: el supervisor lo usa
        # para reintentar el ATEM pasado ATEM_DISCONNECTED_RETRY_AFTER_S.
        self._atem_disconnected_at: float | None = None
        self._atem_monitor = None
        self._fake_atem = None
        self._demo_atem_panel = None
        self._atem_panel = None          # DemoAtemPanel (demo/sim) or AtemAdminPanel (production)
        self._atem_write_adapter = None  # ATEMWriteAdapter in production; None in demo/sim
        self._btn_atem = None
        self._btn_atem_dot = None
        self._last_atem_program: int | None = None
        self._pip_active: bool = False
        self._pending_admin_restart: list | None = None
        self._pending_admin_restart_cwd: str = ""
        self._atem_dispatcher = ATEMDispatcher(
            session_provider=lambda: self.session_active,
            on_action=self._on_atem_action,
        )
        self._pip_nudge_svc = self._build_pip_nudge_service()
        from ui.pip_nudge_wiring import wire_pip_nudge_activity
        wire_pip_nudge_activity(self)
        self._bus.subscribe(EventType.PRESET_SAVE_REQUESTED, self._on_preset_save_requested_feedback)
        self._bus.subscribe(EventType.PRESET_SAVED, self._on_preset_saved_feedback)
        self._start_atem_monitor()
        self._build_demo_atem_panel()
        self._build_atem_button()
        # Re-raise the login overlay: _build_atem_button() calls btn.raise_()/dot.raise_()
        # which would otherwise push the ATEM button above the login overlay.
        if hasattr(self, '_login_overlay') and not self._login_overlay.isHidden():
            self._login_overlay.raise_()

        # Auto-apagado por inactividad (2 horas)
        self._inactivity_timer = QTimer(self)
        self._inactivity_timer.timeout.connect(self._check_inactivity)
        self._inactivity_timer.start(60_000)  # comprueba cada minuto

        # Monitor de pantalla + botón GPIO: preguntan si apagar cámaras al apagarse la pantalla
        self._screen_dialog_active = False
        self._screen_monitor: ScreenMonitor | None = None
        self._gpio_monitor: GpioMonitor | None = None
        if ScreenMonitor.is_available():
            self._screen_monitor = ScreenMonitor(self)
            self._screen_monitor.screen_turned_off.connect(self._on_screen_turned_off)
            self._screen_monitor.start()
        if GpioMonitor.is_available():
            self._gpio_monitor = GpioMonitor(parent=self)
            self._gpio_monitor.button_pressed.connect(self._on_screen_turned_off)
            self._gpio_monitor.start()

        # Flag que evita reinicios durante el cierre de la aplicación.
        self._shutting_down = False
        # True sólo tras completar splash: en login/splash no se ofrece opción
        # de apagar cámaras porque la sesión de trabajo no ha comenzado.
        self._normal_work_active = False
        self._supervisor = self._build_supervisor()

    # ─────────────────────────────────────────────────────────────────────
    # Overlays de inicio
    # ─────────────────────────────────────────────────────────────────────

    def _build_overlays(self):
        from ui.login_screen import LoginScreen
        # El login se muestra SIEMPRE, también en simulación: sim solo cambia las
        # IPs de cámara, no la autenticación ni el rol. Cada arranque parte de
        # Operador (cuenta atrás de 10s) y exige cambiar a Admin explícitamente —
        # nunca se reutiliza un rol admin persistido para entrar.
        self._login_overlay = LoginScreen(parent=self)
        self._login_overlay.setGeometry(0, 0, 1920, 1080)
        self._login_overlay.raise_()
        self._login_overlay.login_successful.connect(self._on_login_done)
        self._login_overlay.exit_requested.connect(self.close)
        self._build_seat_action_overlay()

    def _build_seat_action_overlay(self):
        """Crea los botones flotantes ✓ y ✕ para confirmar/cancelar guardado de preset."""
        self._btn_save_seat = QPushButton('✓', self)
        self._btn_save_seat.setFixedSize(40, 40)
        self._btn_save_seat.setStyleSheet(
            "QPushButton { background: #2e7d32; border-radius: 20px;"
            " font: bold 18px; color: white; border: none; }"
            "QPushButton:pressed { background: #1b5e20; }"
        )
        self._btn_save_seat.clicked.connect(lambda: self._exit_seat_selection(save=True))
        self._btn_save_seat.hide()

        self._btn_cancel_seat = QPushButton('✕', self)
        self._btn_cancel_seat.setFixedSize(40, 40)
        self._btn_cancel_seat.setStyleSheet(
            "QPushButton { background: #c62828; border-radius: 20px;"
            " font: bold 18px; color: white; border: none; }"
            "QPushButton:pressed { background: #8b1a1a; }"
        )
        self._btn_cancel_seat.clicked.connect(lambda: self._exit_seat_selection(save=False))
        self._btn_cancel_seat.hide()

    def _on_login_done(self):
        from ui.splash_screen import SplashScreen
        from runtime.path_resolver import RuntimePathResolver as _rpr

        # Determinar rol post-login:
        # • Login real (operador por cuenta atrás o admin) → el rol lo
        #   decide la credencial usada, expuesto en login_overlay.authenticated_role
        #   (Operador→USER, Admin→ADMIN).
        # • Sim / sin login real → respeta el rol persistido en access_mode.json.
        # El flag legacy de 'restart as admin' solo se consume aquí; el modo de
        # login inicial ya lo decidió LoginScreen a partir de ese flag.
        _admin_flag = _rpr().admin_login_flag
        if _admin_flag.exists():
            try:
                _admin_flag.unlink()
            except OSError:
                pass
        if getattr(self._login_overlay, 'authenticated', False):
            self._access_mode_svc.set_mode(self._login_overlay.authenticated_role)
        # Sincronizar visibilidad de botones de panel con el modo efectivo.
        # Necesario aquí porque el modo puede haber cambiado respecto al que
        # leyó _update_mode_buttons() durante la construcción del panel.
        self._right_panel._update_mode_buttons()

        self._login_overlay.hide()
        self._splash_overlay = SplashScreen(parent=self)
        self._splash_overlay.setGeometry(0, 0, 1920, 1080)
        self._splash_overlay.raise_()
        self._splash_overlay.show()
        self._splash_overlay.startup_complete.connect(self._on_startup_done)
        self._splash_overlay._start_initialization()

    def _on_startup_done(self):
        # The splash completion may already be queued when close begins.
        if getattr(self, '_shutting_down', False):
            return
        self._splash_overlay.hide()
        self._normal_work_active = True
        self._refresh_zoom()
        # Segunda pasada de sincronización: garantiza estado correcto tras el
        # arranque completo (diagnósticos, ATEM, splash) por si algún paso
        # intermedio afectó la visibilidad de widgets.
        self._right_panel._update_mode_buttons()

        import adapters.sim_mode as _sm
        if _sm.is_active():
            if not getattr(self, 'session_active', False):
                self._session.ToggleSession()
            return

        # Producción: ofrecer encender las cámaras al arrancar. El contrato de
        # ciclo de vida prohíbe el arranque AUTOMÁTICO de sesión en boot, pero
        # permite explícitamente una acción de operador vía diálogo confirmado
        # (ver docs/LIFECYCLE_CONTRACT.md). Solo se enciende si el operador acepta.
        self._maybe_prompt_power_on()

    def _maybe_prompt_power_on(self) -> None:
        from ui.startup_power_prompt import maybe_prompt_power_on
        maybe_prompt_power_on(self)

    # ─────────────────────────────────────────────────────────────────────
    # Construcción de la UI
    # ─────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_background()
        self._build_set_overlay()
        self._build_seat_buttons()
        self._build_session_controls()
        self._build_right_panel()
        self._build_names_panel()
        self._seat_names_ctrl._restore_seat_names()
        self._build_table_seats()
        self._build_platform_icons()
        self._build_camera_indicator()
        self._build_mode_buttons()
        self._build_admin_hotspot()
        from ui.persistence_indicator import install
        install(self)

        self.BtnNames.raise_()

        # _mode_border debe existir antes de conectar las señales porque
        # _update_mode_indicator lo referencia en cada pulsación de modo.
        self._mode_border = ModeBorderOverlay(self)
        self._mode_border.raise_()

    def _build_camera_indicator(self):
        self._cam_indicator = CameraIndicator(self)
        self._cam_indicator.set_mode('platform')
        self._cam_indicator.raise_()

    def _build_mode_buttons(self):
        self.BtnCall = QPushButton(self)
        self.BtnCall.setCheckable(True)
        self.BtnCall.setAutoExclusive(True)
        self.BtnCall.setChecked(True)
        self.BtnCall.hide()

        self.BtnSet = QPushButton(self)
        self.BtnSet.setCheckable(True)
        self.BtnSet.setAutoExclusive(True)
        self.BtnSet.hide()

        self.PresetModeGroup = QButtonGroup(self)
        self.PresetModeGroup.addButton(self.BtnCall)
        self.PresetModeGroup.addButton(self.BtnSet)

    def _update_mode_indicator(self, mode: str):
        self._set_overlay.set_mode(mode)
        self._mode_border.set_mode(mode)
        GoButton.set_call_mode(mode == 'call')
        for btn in self.findChildren(GoButton):
            btn._apply_style()
        for btn in self.findChildren(SpecialDragButton):
            btn._apply_style()

    def _build_set_overlay(self):
        self._set_overlay = AuditoriumOverlay(self)
        self._set_overlay.set_mode('call')

    def _build_background(self):
        from pathlib import Path
        bg_path = Path(__file__).resolve().parent / "khptz_background.jpg"
        if not bg_path.exists():
            logger.warning("%s no encontrado — fondo vacío", bg_path)
            return
        pixmap = QPixmap(str(bg_path)).scaled(
            1920, 1080, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        background = QLabel(self)
        background.setPixmap(pixmap)
        background.setGeometry(0, 0, 1920, 1080)
        background.lower()

    def _build_table_seats(self):
        from ui.table_decoration import build_table_decoration
        build_table_decoration(self)

    def _build_platform_icons(self):
        btn_w, btn_h = 110, 115

        # ── Left (preset 2) ───────────────────────────────────────────────
        cx = 562
        renderer = QSvgRenderer(QtCore.QByteArray(SVG_LEFT.encode('utf-8')))
        pix = QPixmap(70, 70)
        pix.fill(Qt.transparent)
        p = QtGui.QPainter(pix)
        renderer.render(p, QtCore.QRectF(0, 0, 70, 70))
        p.end()
        btn = PlatformPresetButton(self)
        btn.setText('Left')
        btn.setIcon(QtGui.QIcon(pix))
        btn.setIconSize(QtCore.QSize(70, 70))
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setGeometry(cx - btn_w // 2, 30, btn_w, btn_h)
        btn.setStyleSheet(
            "QToolButton { background-color: transparent; border: none;"
            " font: bold 13px; color: black; }"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )
        # Tap → CALL (recall); pulsación larga / clic derecho → SET (guardar).
        btn.init_preset_actions(
            2, call_cb=self._call_preset_from_button,
            set_cb=self._confirm_and_set_preset,
        )
        btn.raise_()

        # ── Chairman (preset 1) — ChairmanButton con AsyncEventBus ──────────
        cx = 744
        self._chairman_btn = ChairmanButton(
            bus        = self._bus,
            preset_svc = self._preset_svc,
            svg_data   = SVG_CHAIRMAN,
            icon_w=90, icon_h=90,
            parent=self,
        )
        self._chairman_btn.setGeometry(cx - btn_w // 2, 30, btn_w, btn_h)
        self._chairman_btn.name_assigned.connect(self._seat_names_ctrl._on_seat_name_assigned)
        # Tap → CALL (recall persona/genérico); pulsación larga / clic derecho →
        # SET (guardar). El Chairman es la plataforma principal con PERSONAS:
        # su SET guarda el preset de la persona asignada (no un slot genérico).
        self._chairman_btn.init_preset_actions(
            PRESET_CHAIRMAN_GENERIC,
            call_cb=self._chairman_call,
            set_cb=self._chairman_set,
        )
        self._chairman_btn.raise_()
        setattr(self, "Seat1", self._chairman_btn)

        # ── Right (preset 3) ──────────────────────────────────────────────
        cx = 938
        renderer = QSvgRenderer(QtCore.QByteArray(SVG_RIGHT.encode('utf-8')))
        pix = QPixmap(70, 70)
        pix.fill(Qt.transparent)
        p = QtGui.QPainter(pix)
        renderer.render(p, QtCore.QRectF(0, 0, 70, 70))
        p.end()
        btn = PlatformPresetButton(self)
        btn.setText('Right')
        btn.setIcon(QtGui.QIcon(pix))
        btn.setIconSize(QtCore.QSize(70, 70))
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setGeometry(cx - btn_w // 2, 30, btn_w, btn_h)
        btn.setStyleSheet(
            "QToolButton { background-color: transparent; border: none;"
            " font: bold 13px; color: black; }"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )
        # Tap → CALL (recall); pulsación larga / clic derecho → SET (guardar).
        btn.init_preset_actions(
            3, call_cb=self._call_preset_from_button,
            set_cb=self._confirm_and_set_preset,
        )
        btn.raise_()

        # ── Platform 2 (preset 132) — opcional, esquina superior derecha ───
        # Sólo se construye si el operador lo activó (display_prefs).
        self._platform2_btn = None
        if _load_second_platform_enabled():
            self._build_second_platform_icon()

    def apply_second_platform_visibility(self, enabled: bool) -> None:
        """Show or hide the Platform 2 button live (no restart needed).

        Builds the button on first enable; subsequent toggles just show/hide it.
        Called by the Settings dialog after persisting the preference.
        """
        if enabled:
            if getattr(self, "_platform2_btn", None) is None:
                self._build_second_platform_icon()
            else:
                self._platform2_btn.show()
                self._platform2_btn.raise_()
        else:
            btn = getattr(self, "_platform2_btn", None)
            if btn is not None:
                btn.hide()

    def _build_second_platform_icon(self):
        """Botón pequeño 'Platform 2' (preset 132) en la esquina superior derecha.

        Icono de plataforma reducido; actúa sobre la cámara platform como el
        resto de presets de plataforma (PRESET_PLATFORM_2 ∈ PLATFORM_PRESETS).
        """
        renderer = QSvgRenderer(QtCore.QByteArray(SVG_CHAIRMAN.encode('utf-8')))
        pix = QPixmap(44, 44)
        pix.fill(Qt.transparent)
        p = QtGui.QPainter(pix)
        renderer.render(p, QtCore.QRectF(0, 0, 44, 44))
        p.end()
        btn = PlatformPresetButton(self)
        btn.setText('Platform 2')
        btn.setIcon(QtGui.QIcon(pix))
        btn.setIconSize(QtCore.QSize(44, 44))
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setGeometry(1010, 24, 72, 78)
        btn.setStyleSheet(
            "QToolButton { background-color: transparent; border: none;"
            " font: bold 11px; color: black; }"
            "QToolButton:pressed { background-color: rgba(0,0,0,40); }"
        )
        # Tap → CALL (recall); pulsación larga / clic derecho → SET (guardar).
        btn.init_preset_actions(
            PRESET_PLATFORM_2, call_cb=self._call_preset_from_button,
            set_cb=self._confirm_and_set_preset,
        )
        # show() es necesario cuando se construye en vivo (ventana ya visible);
        # en el arranque es inocuo porque el padre aún no se ha mostrado.
        btn.show()
        btn.raise_()
        self._platform2_btn = btn

    # ─────────────────────────────────────────────────────────────────────
    # Seat buttons
    # ─────────────────────────────────────────────────────────────────────

    def _build_seat_buttons(self):
        if self._layout_svc is None:
            logger.error("_build_seat_buttons: LayoutService not available — no seat buttons created")
            return
        seats = self._layout_svc.visible_seats()
        self._seat_registry = SeatRegistry()
        for seat in seats:
            seat_number = seat.preset
            x, y = seat.x, seat.y
            if seat.type == "special" or seat_number in (128, 129, 130, 131):
                button = build_special_seat_button(seat_number, x, y, parent=self, label=seat.label)
                button.init_preset_actions(
                    seat_number,
                    call_cb=self._call_preset_from_button,
                    set_cb=self._confirm_and_set_preset,
                )
            else:
                button = GoButton(seat_number, self)
                button.move(x, y)
                button.init_preset_actions(
                    seat_number,
                    call_cb=self._call_preset_from_button,
                    set_cb=self._confirm_and_set_preset,
                )
            button._layout_seat_id = seat.id
            button._layout_label = seat.label
            if isinstance(button, GoButton):
                button.setText(seat.label)
            button.name_assigned.connect(
                lambda _number, name, seat_id=seat.id:
                    self._seat_names_ctrl._on_seat_name_assigned(seat_id, name))
            self._seat_registry.add(seat, button)
            button._call_cb = lambda _preset, seat_id=seat.id: self._dispatch_layout_seat(seat_id, InputType.TAP)
            button._set_cb = lambda _preset, seat_id=seat.id: self._dispatch_layout_seat(seat_id, InputType.LONG_PRESS)
            if seat_number == 0:
                button.setToolTip('No camera memory assigned. Calibration required.')
        # Existing preset-based paths keep only unambiguous, assigned aliases.
        for preset in {seat.preset for seat in seats if seat.preset > 0}:
            button = self._seat_registry.legacy(preset)
            if button is not None:
                setattr(self, f"Seat{preset}", button)

    def _build_session_controls(self):
        self.BtnSession = QPushButton('\u23fb', self)
        self.BtnSession.setGeometry(10, 10, 50, 50)
        self.BtnSession.setToolTip('Start Session: Power ON both cameras and go Home')
        self.BtnSession.setStyleSheet(SessionController._STYLE_BTN_OFF)
        self.BtnSession.clicked.connect(self._session.ToggleSession)
        self.BtnSession.setVisible(False)

        self.SessionStatus = QLabel('OFF', self)
        self.SessionStatus.setGeometry(68, 22, 60, 20)
        self.SessionStatus.setStyleSheet("font: bold 12px; color: #8b1a1a")
        self.SessionStatus.setVisible(False)

        self.BtnNames = QPushButton(self)
        self.BtnNames.setGeometry(1392, 15, 50, 40)
        self.BtnNames.setCheckable(True)
        self.BtnNames.setToolTip('Attendees panel')
        self.BtnNames.setStyleSheet(
            "QPushButton { background: white; border: 2px solid #1976D2;"
            " border-radius: 6px; }"
            "QPushButton:checked { background: #1976D2; }"
            "QPushButton:pressed  { background: #e3f2fd; }"
        )
        _pe_svg = QSvgRenderer(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'person-edit.svg'))
        _pe_pix = QPixmap(26, 26)
        _pe_pix.fill(Qt.transparent)
        _p = QtGui.QPainter(_pe_pix)
        _pe_svg.render(_p)
        _p.end()
        self.BtnNames.setIcon(QtGui.QIcon(_pe_pix))
        self.BtnNames.setIconSize(_pe_pix.size())
        self.BtnNames.clicked.connect(self._toggle_names_panel)

    def _build_admin_hotspot(self):
        """Hidden transparent hotspot (top-left corner) → Settings in admin mode.

        Production only. A fully transparent button lets a technician reach the
        configuration dialog from a locked-down operator screen without exposing
        a visible control; the password gate (RoleElevationOverlay) protects
        access. Demo/simulation skip it — those profiles expose admin access
        directly and bypass login.

        Stacked under BtnSession so the session toggle keeps priority where the
        two overlap; the rest of the corner stays active when no session button
        is shown. The full-window overlays in this corner are
        WA_TransparentForMouseEvents, so the hotspot receives clicks as BtnSession
        already does.
        """
        if os.environ.get("KHPTZ_PROFILE", "production") != "production":
            return
        btn = QPushButton(self)
        btn.setGeometry(0, 0, 64, 64)
        btn.setFlat(True)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet("QPushButton { background: transparent; border: none; }")
        btn.clicked.connect(self._open_admin_settings)
        btn.stackUnder(self.BtnSession)
        self._admin_hotspot = btn

    def _zoom_to_speed(self, zoom: int) -> int:
        # zoom %     velocidad   (~% de TILT_SPEED_MAX=20; pan puede llegar a 24 via _pan_cap)
        # ─────────────────────────────────────────
        #   0 –  9      20          100 %
        #  10 – 18      19           95 %
        #  19 – 27      18           90 %
        #  28 – 36      16           80 %
        #  37 – 45      15           75 %
        #  46 – 54      14           70 %
        #  55 – 63      13           65 %
        #  64 – 72      11           55 %
        #  73 – 81      10           50 %
        #  82 – 90       9           45 %
        #  91 – 100      8           40 %
        return min(zoom_to_raw_speed(zoom), self._tilt_cap)

    # ── Watchdog de velocidad VISCA ───────────────────────────────────────────

    @staticmethod
    def _fresh_watchdog_state() -> dict:
        return fresh_channel_state()

    def _reset_watchdog_state(self) -> None:
        """Restablece caps y estado al iniciar sesión."""
        self._pan_cap        = PAN_SPEED_MAX
        self._tilt_cap       = TILT_SPEED_MAX
        self._zoom_drive_cap = ZOOM_DRIVE_MAX
        self._camera_port.pan_cap        = self._pan_cap
        self._camera_port.tilt_cap       = self._tilt_cap
        self._camera_port.zoom_drive_cap = self._zoom_drive_cap
        self._watchdog_state = {
            'move':       self._fresh_watchdog_state(),
            'zoom_drive': self._fresh_watchdog_state(),
        }
        logger.info("Watchdog VISCA: estado y caps restablecidos al inicio de sesión")

    def _on_worker_ready(self, worker) -> None:
        from ui.camera_led_wiring import wire_camera_worker
        wire_camera_worker(self, worker)

    def _on_visca_speed_error(self, ip: str, cmd_type: str) -> None:
        # Shell extraído a ui/visca_watchdog.py (ratchet anti god-object);
        # la decisión es de domain/adaptive_speed. Comportamiento idéntico.
        from ui.visca_watchdog import on_visca_speed_error
        on_visca_speed_error(self, ip, cmd_type)

    def _build_demo_atem_panel(self) -> None:
        """Create DemoAtemPanel when running in demo/simulation mode (starts hidden)."""
        if self._fake_atem is None:
            return
        from ui.demo_atem_panel import DemoAtemPanel
        self._demo_atem_panel = DemoAtemPanel(
            fake_atem=self._fake_atem,
            dispatcher=self._atem_dispatcher,
            pip_nudge_svc=self._pip_nudge_svc,
            pip_save_fn=self._save_nudge_to_config,
            parent=self,
        )
        self._demo_atem_panel.setGeometry(60, 80, 480, 460)
        self._demo_atem_panel.hide()
        self._atem_panel = self._demo_atem_panel
        logger.info("[DEMO] DemoAtemPanel created (hidden — use ATEM button to show)")

    def _atem_is_configured(self) -> bool:
        """True when the ATEM switcher has a valid IP configured.

        Gates ATEM automation surfaces (the floating panel's PiP automation and
        the Settings automation section): without a switcher there is nothing to
        automate. Reads the live config.ATEM object so it reflects edits made in
        the config dialog.
        """
        from config import ATEM as _atem_cfg, is_valid_ip
        return is_valid_ip(_atem_cfg.ip)

    def _build_atem_button(self) -> None:
        """Create the ATEM panel toggle button and its connection-state dot indicator."""
        import os as _os
        profile = _os.environ.get("KHPTZ_PROFILE", "production")
        is_demo = profile in ("demo", "simulation") or self._fake_atem is not None

        if not is_demo and self._atem_panel is None:
            try:
                from ui.atem_admin_panel import AtemAdminPanel
                from application.atem_diagnostics_service import AtemDiagnosticsService
                from application.atem_command_service import AtemCommandService
                from adapters.atem_write_adapter import ATEMWriteAdapter
                _write_adapter = ATEMWriteAdapter(ip=ATEM.ip)
                self._atem_write_adapter = _write_adapter
                panel = AtemAdminPanel(
                    diagnostics_svc=AtemDiagnosticsService(_write_adapter),
                    command_svc=AtemCommandService(_write_adapter),
                    role_provider=lambda: self._access_mode_svc.mode,
                    pip_automation_provider=lambda: self._atem_dispatcher.pip_automation_enabled,
                    pip_automation_setter=self._atem_dispatcher.set_pip_automation_enabled,
                    atem_configured_provider=self._atem_is_configured,
                    pip_nudge_svc=self._pip_nudge_svc,
                    pip_set_fn=self.pip_set,
                    pip_save_fn=self._save_nudge_to_config,
                    on_close=self._close_atem_panel,
                    parent=self,
                )
                panel.setGeometry(60, 80, 480, 460)
                panel.hide()
                self._atem_panel = panel
            except Exception as exc:
                logger.warning("[ATEM] AtemAdminPanel unavailable: %s", exc)

        btn = QPushButton("ATEM", self)
        btn.setGeometry(1392, 63, 50, 40)
        btn.setCheckable(True)
        btn.setToolTip("ATEM switcher panel")
        btn.setStyleSheet(
            "QPushButton { background: white; border: 2px solid #37474F;"
            " border-radius: 6px; font: bold 9px 'Segoe UI', sans-serif; color: #37474F; }"
            "QPushButton:checked { background: #37474F; color: white; }"
            "QPushButton:disabled { background: #eee; border-color: #bbb; color: #bbb; }"
            "QPushButton:pressed  { background: #eceff1; }"
        )
        btn.clicked.connect(self._toggle_atem_panel)
        btn.setVisible(self._atem_panel is not None)
        self._btn_atem = btn

        dot = QLabel(self)
        dot.setGeometry(1433, 56, 12, 12)
        dot.setVisible(self._atem_panel is not None)
        self._btn_atem_dot = dot

        self._update_atem_button(self._atem_state)
        btn.raise_()
        dot.raise_()

    def _close_atem_panel(self) -> None:
        """Hide the ATEM panel and reset the toggle button. Used by the panel's
        own close (✕) button, which must work even when the toggle is disabled
        because the switcher is unreachable."""
        if self._atem_panel is not None:
            self._atem_panel.hide()
        if self._btn_atem is not None:
            self._btn_atem.setChecked(False)

    def _toggle_atem_panel(self) -> None:
        if self._atem_panel is None:
            self._close_atem_panel()
            return
        # Demo/sim (FakeATEM): the panel stays reachable even disconnected —
        # it owns the Reconnect control (#921). Live hardware requires a
        # verified operational monitor.
        if self._fake_atem is None and not self.atem_operational():
            self._close_atem_panel()
            return
        visible = self._atem_panel.isVisible()
        if not visible and self._atem_write_adapter is not None:
            # connect_async() guards against spawning a second thread if already
            # connecting or connected — safe to call on every panel open.
            self._atem_write_adapter.connect_async()
        self._atem_panel.setVisible(not visible)
        if self._btn_atem is not None:
            self._btn_atem.setChecked(not visible)

    def _update_atem_button(self, state) -> None:
        if self._btn_atem is None or self._btn_atem_dot is None:
            return
        from ui.atem_button_state import apply_atem_button_state
        apply_atem_button_state(
            self._btn_atem, self._btn_atem_dot, self._atem_panel, state,
            self._fake_atem, operative=self.atem_operational())

    def _cache_atem_program(self, input_id: int) -> None:
        self._last_atem_program = input_id

    # ── PiP state — notificación a paneles ───────────────────────────────────

    def _on_pip_state_changed(self, pip_state) -> None:
        """Recibe ATEMPiPState desde ATEMMonitor (producción) y notifica al panel ATEM."""
        # Ignora señales obsoletas de un monitor sustituido/detenido.
        if self._atem_monitor is not None:
            sender = self.sender()
            if sender is not None and sender is not self._atem_monitor:
                return
        active = pip_state is not None and pip_state.enabled
        self._pip_active = active
        self._notify_pip_state(active)

    def _notify_pip_state(self, active: bool) -> None:
        """Propaga el estado PiP al panel ATEM si lo soporta."""
        if self._atem_panel is not None and hasattr(self._atem_panel, "set_pip_state"):
            self._atem_panel.set_pip_state(active)

    def pip_set(self, state: bool) -> None:
        """Envía un comando PiP al ATEM (demo o producción).

        Llamado desde AtemAdminPanel cuando el operador activa/desactiva el PiP.
        """
        if self._atem_write_adapter is not None:
            result = self._atem_write_adapter.set_pip_enabled(state)
            if not result.ok:
                logger.warning("ATEM PiP request failed: %s", result.message)
            return  # Only monitor telemetry confirms the production state.
        else:
            from domain.atem_state import ATEMPiPState
            self._atem_dispatcher.on_pip_changed(ATEMPiPState(enabled=state, source=None))
        # Demo has no hardware telemetry; update its local state immediately.
        self._pip_active = state
        self._notify_pip_state(state)

    def _save_nudge_to_config(self, pan_speed: int, direction: str, duration_ms: int) -> None:
        """Persiste la configuración de nudge en config.yaml."""
        try:
            from config.effective import patch_runtime_config as patch_config_yaml
            from runtime.path_resolver import RuntimePathResolver
            resolver = RuntimePathResolver()
            patch_config_yaml(
                resolver.config_dir / "config.yaml",
                atem_pip_nudge={
                    "pan_speed": pan_speed,
                    "direction": direction,
                    "duration_ms": duration_ms,
                },
            )
            logger.info("[PiPNudge] configuración guardada en config.yaml")
        except Exception as exc:
            logger.warning("[PiPNudge] no se pudo guardar en config.yaml: %s", exc)

    def _build_right_panel(self):
        from ui.right_panel import RightPanel
        from adapters.input.joystick_adapter import JoystickAdapter
        self._right_panel = RightPanel(self)
        _joy = JoystickAdapter(
            bus=self._bus,
            active_camera_fn=lambda: 1 if self.Cam1.isChecked() else 2,
        )
        self._right_panel.connect_joystick(
            handlers=_joy.handlers(),
            stop_handler=_joy.stop,
            speed_provider=lambda: self._zoom_to_speed(self.ZoomSlider.value()),
        )
        self._right_panel.set_joystick_mode('platform')
        from ui.stop_all_wiring import connect_stop_all
        connect_stop_all(self)
        self._update_focus_ui()
        self._update_exposure_ui()

    def _open_config_dialog(self):
        from adapters.sim_mode import is_active
        simulated = is_active()
        for cam in (CAM1, CAM2):
            cam.check = "Green" if simulated or self._cameras.is_connected(cam.ip) else "Red"
        dlg = ConfigDialog(parent=self)
        dlg.exec_()
        self._right_panel._update_mode_buttons()

    def _open_admin_settings(self):
        """Hidden-hotspot entry point: open Settings in administrator mode.

        If the current role already has configuration access, open Settings
        directly. Otherwise show the password overlay; on the correct admin
        password, elevate to Admin and then open Settings. Reuses the same
        RoleElevationOverlay and ConfigDialog flow as the right-panel buttons —
        no separate admin path.
        """
        _SETTINGS_ROLES = {OperatingMode.ADMIN}
        if self._access_mode_svc.mode in _SETTINGS_ROLES:
            self._open_config_dialog()
            return
        from runtime.secret_manager import password_is_configured
        if not password_is_configured():
            QMessageBox.warning(
                self, "No password configured",
                "No password is set up.\n"
                "Run: python3 setup_password.py",
            )
            return
        if not hasattr(self, '_admin_settings_overlay'):
            from ui.role_elevation_overlay import RoleElevationOverlay
            self._admin_settings_overlay = RoleElevationOverlay(
                parent=self,
                on_success=self._on_admin_settings_elevation_success,
                on_cancel=lambda: None,
            )
        self._admin_settings_overlay.show_overlay()

    def _on_admin_settings_elevation_success(self):
        """Correct admin password via the hidden hotspot: elevate, open Settings."""
        self._on_role_elevation_success()
        self._open_config_dialog()

    def _enter_admin_mode_inline(self):
        """Muestra el overlay de elevación de rol sobre la ventana actual."""
        from runtime.secret_manager import password_is_configured
        if not password_is_configured():
            QMessageBox.warning(
                self, "No password configured",
                "No password is set up.\n"
                "Run: python3 setup_password.py",
            )
            return
        if not hasattr(self, '_role_elevation_overlay'):
            from ui.role_elevation_overlay import RoleElevationOverlay
            self._role_elevation_overlay = RoleElevationOverlay(
                parent=self,
                on_success=self._on_role_elevation_success,
                on_cancel=lambda: None,
            )
        self._role_elevation_overlay.show_overlay()

    def _on_role_elevation_success(self):
        """Callback tras contraseña correcta: sube a ADMIN sin reiniciar."""
        self._access_mode_svc.set_mode(OperatingMode.ADMIN)
        self._right_panel._update_mode_buttons()
        logger.info("Rol cambiado a ADMIN (overlay inline)")

    def _exit_admin_mode(self):
        """Baja el rol a USER inline — sin contraseña ni reinicio."""
        self._access_mode_svc.set_mode(OperatingMode.USER)
        self._right_panel._update_mode_buttons()
        logger.info("Rol cambiado a USER (inline)")

    def _restart_as_admin(self):
        """Escribe el flag de admin y cierra la app para relanzarla con login.

        El nuevo proceso se lanza DESPUÉS de que closeEvent finalice y
        acepte el cierre — nunca antes de que el operador confirme el diálogo
        de shutdown y se detenga el hardware (cámaras, ATEM, bus de eventos).
        """
        import sys
        from pathlib import Path
        from runtime.path_resolver import RuntimePathResolver
        try:
            RuntimePathResolver().admin_login_flag.write_text('1', encoding='utf-8')
        except OSError as exc:
            logger.exception("No se pudo escribir admin_login.flag: %s", exc)
            return
        # Guardar el comando para ejecutarlo en closeEvent tras event.accept().
        self._pending_admin_restart = [sys.executable, str(Path(__file__).parent.parent / 'main.py')]
        self._pending_admin_restart_cwd = str(Path(__file__).parent.parent)
        self.close()  # abre el diálogo de shutdown; el Popen se hace al final

    # ─────────────────────────────────────────────────────────────────────
    # Panel de asistentes
    # ─────────────────────────────────────────────────────────────────────

    def _build_names_panel(self):
        self._names_panel = NamesPanel(
            self._names_list, self._seat_names_ctrl._on_names_list_changed,
            self._seat_names_ctrl._clear_all_seats, parent=self,
            recall_by_name_cb=self._recall_seat_by_name,
            undo_cb=self._seat_names_ctrl.undo_last_assignment)
        self._names_panel.hide()

    def _recall_seat_by_name(self, query: str) -> None:
        """Recall por nombre (B3): lleva la cámara al asiento de la persona buscada.

        Coincidencia exacta (sin distinguir mayúsculas) primero; si no, subcadena.
        Sin coincidencia → no hace nada (la persona no está sentada en ningún asiento).
        """
        q = query.strip().casefold()
        if not q:
            return
        match_key = next(
            (k for k, n in self._seat_names.items() if n.casefold() == q), None)
        if match_key is None:
            match_key = next(
                (k for k, n in self._seat_names.items() if q in n.casefold()), None)
        if match_key is None:
            return
        button = seat_button(self, match_key)
        if button is not None and hasattr(button, '_layout_seat_id'):
            seat = self._layout_svc.seat_by_id(button._layout_seat_id)
            if seat is not None and seat.preset > 0:
                self._dispatch_layout_seat(seat.id, InputType.TAP)
            return
        registry = getattr(self, '_seat_registry', None)
        if isinstance(registry, SeatRegistry):
            try:
                if int(match_key) in registry._presets:
                    return  # Unresolved/ambiguous layout alias, never guess.
            except ValueError:
                pass
        try:
            self._dispatch_preset_action(int(match_key), InputType.TAP)
        except ValueError:
            return

    def _toggle_names_panel(self, checked: bool):
        if checked:
            self._names_panel.set_edit_mode(True)
            self._names_panel.raise_()
            self._names_panel.show()
            self._update_mode_indicator('set')
            GoButton.set_call_mode(False)
        else:
            self._names_panel.set_edit_mode(False)
            self._names_panel.hide()
            self._update_mode_indicator('call')
            GoButton.set_call_mode(True)
        for btn in self.findChildren(GoButton):
            btn._apply_style()
        for btn in self.findChildren(SpecialDragButton):
            btn._apply_style()

    def _chairman_call(self, _preset: int = PRESET_CHAIRMAN_GENERIC):
        """Tap en Chairman → recall: la persona asignada, o el preset genérico."""
        name = self._chairman_btn.assigned_name
        if name:
            self._bus.emit(EventType.CHAIRMAN_ASSIGNED, name=name)
        else:
            self._dispatch_preset_action(PRESET_CHAIRMAN_GENERIC, InputType.TAP)

    def _chairman_set(self, _preset: int = PRESET_CHAIRMAN_GENERIC):
        """Pulsación larga en Chairman → SET.

        La plataforma principal trabaja con PERSONAS: si hay una persona
        asignada, guarda el preset de esa persona (mismo flujo que el botón
        💾 Save position). Si no hay persona, guarda el preset genérico de
        plataforma (slot 1) con el diálogo de confirmación estándar.
        """
        if self._chairman_btn.assigned_name:
            self._chairman_btn.request_person_save()
        else:
            self._dispatch_preset_action(PRESET_CHAIRMAN_GENERIC, InputType.LONG_PRESS)

    def _current_operating_mode(self) -> OperatingMode:
        """Devuelve el modo operativo actual para la política CALL/SET.

        name_edit es un modo de trabajo temporal — bloquea acciones de cámara.
        El rol (user/admin) viene del AccessModeService.
        """
        if self.BtnNames.isChecked():
            return OperatingMode.NAME_EDIT
        return self._access_mode_svc.mode

    def _is_camera_available(self) -> bool:
        """True si la cámara actualmente seleccionada tiene conexión activa."""
        if self.Cam1.isChecked():
            return self.Cam1._connected
        return self.Cam2._connected

    def _flash_blocked(self, widget, duration_ms: int = 400) -> None:
        """Breve flash rojo sobre widget cuando una acción de preset es bloqueada."""
        orig = widget.styleSheet()
        widget.setStyleSheet(orig + " background-color: #7a1a1a;")
        widget_ref = weakref.ref(widget)

        def restore_style():
            target = widget_ref()
            if target is not None and not sip.isdeleted(target):
                target.setStyleSheet(orig)

        QTimer.singleShot(duration_ms, restore_style)

    def _dispatch_preset_action(
        self,
        preset_number: int,
        input_type: InputType = InputType.LEFT_CLICK,
        *, seat_id: str | None = None,
    ) -> None:
        """
        Único punto de despacho para todas las acciones de preset iniciadas por usuario.

        Delega la validación CALL/SET en ApplicationController. La UI solo gestiona
        el feedback visual y el flujo de confirmación para acciones SET.
        """
        cam = 1 if self.Cam1.isChecked() else 2

        if preset_number <= 0:
            return
        button = getattr(self, f"Seat{preset_number}", None)
        stable_id = seat_id if seat_id is not None else getattr(button, '_layout_seat_id', preset_number)
        result = self._app_ctrl.recall_seat(
            seat_id=stable_id,
            preset=preset_number,
            input_type=input_type,
            cam=cam,
            mode=self._current_operating_mode(),
            session_active=self.session_active,
            camera_available=self._is_camera_available(),
        )

        if result.error_code == "set_action":
            # SET: confirmar con el usuario y salvar preset (permanece en UI).
            if preset_number in PLATFORM_PRESETS:
                session_generation = self._session._session_generation
                reply = QMessageBox.question(
                    self,
                    "Save Camera Position",
                    f"Save current camera position as preset {preset_number}?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.Yes:
                    # The modal event loop can process inactivity shutdown or
                    # session restart while the confirmation is on screen.
                    if (self._shutting_down or not self.session_active
                            or self._session._session_generation != session_generation):
                        logger.info("Preset save cancelled: session changed during confirmation")
                        return
                    self._bus.emit(
                        EventType.PRESET_SAVE_SLOT,
                        camera=cam,
                        slot=preset_number,
                    )
            else:
                self._enter_seat_selection(preset_number)
            return

        if not result.ok:
            self._handle_recall_blocked(result.error_code, preset_number)

    def _handle_recall_blocked(self, reason_code: str, preset_number: int) -> None:
        """Feedback visual cuando ApplicationController bloquea una acción de recall."""
        if reason_code in ("names_mode_data_only", "name_edit_no_camera_action"):
            self._flash_blocked(self.BtnNames)
        elif reason_code == "camera_unavailable":
            self._flash_blocked(self.Cam1 if self.Cam1.isChecked() else self.Cam2)
        elif reason_code == "session_inactive":
            self._flash_blocked(self.BtnSession)
        elif reason_code in ("operator_no_set", "role_no_set"):
            logger.info(
                "SET bloqueado: rol sin permiso de SET — preset %d", preset_number)
            btn_to_flash = (
                self._right_panel._btn_gear
                if self._right_panel._btn_gear.isVisible()
                else self._right_panel._btn_enter_admin
            )
            self._flash_blocked(btn_to_flash)

    def _dispatch_layout_seat(self, seat_id: str, input_type: InputType) -> None:
        seat = self._layout_svc.seat_by_id(seat_id)
        if seat is None or not seat.visible or seat.preset <= 0:
            return
        # Remaining SET/feedback paths are preset-based. Until they migrate,
        # reject ambiguous memories instead of choosing a camera or widget.
        if self._seat_registry.legacy(seat.preset) is None:
            return
        self._dispatch_preset_action(seat.preset, input_type, seat_id=seat.id)

    def _call_preset_from_button(self, preset_number: int) -> None:
        """GoButton tap/left-click → CALL via unified dispatch."""
        self._dispatch_preset_action(preset_number, InputType.TAP)

    def _confirm_and_set_preset(self, preset_number: int) -> None:
        """GoButton right-click/long-press → SET via unified dispatch."""
        self._dispatch_preset_action(preset_number, InputType.LONG_PRESS)

    # ── Selección visual de asiento para guardar preset ───────────────────

    def _visible_preset_set(self) -> set:
        """Return the set of visible seat preset numbers from the loaded layout."""
        if self._layout_svc is not None:
            return {s.preset for s in self._layout_svc.visible_seats()}
        return set()

    def _enter_seat_selection(self, preset_number: int) -> None:
        if self._seat_pending is not None:
            self._exit_seat_selection(save=False)

        self._seat_pending = preset_number

        # Auditorium/special seats (4-131) always live on CAM2; ensure the
        # joystick is controlling CAM2 so the user moves the right camera.
        if preset_number not in PLATFORM_PRESETS and not self.Cam2.isChecked():
            self.Cam2.click()

        self._seat_pending_camera = 1 if self.Cam1.isChecked() else 2
        for n in self._visible_preset_set():
            btn = getattr(self, f"Seat{n}", None)
            if btn is None:
                continue
            if n == preset_number:
                btn.set_preset_pending(True)
            else:
                btn.set_dimmed(True)

        seat_btn = getattr(self, f"Seat{preset_number}", None)
        if seat_btn is not None:
            sx = seat_btn.x()
            sy = seat_btn.y()
            sw = seat_btn.width()
            sh = seat_btn.height()
            gap = 8
            bx = sx + sw + gap
            if bx + 40 > 1440:
                bx = sx - 40 - gap
            cy = sy + sh // 2
            self._btn_save_seat.move(bx, cy - 44)
            self._btn_cancel_seat.move(bx, cy + 4)

        self._btn_save_seat.raise_()
        self._btn_cancel_seat.raise_()
        self._btn_save_seat.show()
        self._btn_cancel_seat.show()

    def _exit_seat_selection(self, save: bool) -> None:
        preset_number = self._seat_pending
        pending_camera = self._seat_pending_camera
        self._seat_pending = None
        self._seat_pending_camera = None
        self._btn_save_seat.hide()
        self._btn_cancel_seat.hide()

        for n in self._visible_preset_set():
            btn = getattr(self, f"Seat{n}", None)
            if btn is None:
                continue
            if hasattr(btn, 'set_dimmed'):
                btn.set_dimmed(False)
            if hasattr(btn, 'set_preset_pending'):
                btn.set_preset_pending(False)

        if save and preset_number is not None:
            cam = 1 if self.Cam1.isChecked() else 2
            if cam != pending_camera:
                logger.warning("Seat preset save cancelled: camera changed during selection")
                self._flash_blocked(self.Cam1 if cam == 1 else self.Cam2)
                return
            self._bus.emit(EventType.PRESET_SAVE_SLOT, camera=pending_camera, slot=preset_number)
            seat_btn = getattr(self, f"Seat{preset_number}", None)
            if seat_btn is not None and hasattr(seat_btn, 'show_saved'):
                seat_btn.show_saved()

    def _find_seat_button_by_name(self, name: str):
        for seat in range(1, 128):
            btn = getattr(self, f"Seat{seat}", None)
            if btn is not None and getattr(btn, "assigned_name", None) == name:
                return btn
        return None

    def _on_preset_save_requested_feedback(self, event) -> None:
        name = event.payload.get("name", "")
        btn = self._find_seat_button_by_name(name)
        if btn is not None:
            btn.show_saving()

    def _on_preset_saved_feedback(self, event) -> None:
        name = event.payload.get("name", "")
        btn = self._find_seat_button_by_name(name)
        if btn is not None:
            btn.show_saved()

    def _build_supervisor(self):
        """Registra los workers y arranca el supervisor de threads
        (cableado extraído a core/supervisor_wiring.py — presupuesto god-object)."""
        from core.supervisor_wiring import build_supervisor
        return build_supervisor(self)

    def _restart_atem_monitor(self):
        # Llamado desde el hilo del supervisor: delegar al hilo principal de Qt.
        QTimer.singleShot(0, self._do_restart_atem_monitor)

    def _start_atem_monitor(self):
        import adapters.sim_mode as _sim
        from domain.atem_runtime_policy import is_fake_atem_mode
        self._atem_state = None
        self._atem_disconnected_at = None
        self._atem_verified_monitor = None
        self._atem_dispatcher.reset_input_tracking()

        # Always clean up FakeATEM callbacks from a previous demo/sim session
        # before deciding which path to take. Without this, switching from
        # demo → production leaves stale callbacks on the dispatcher/panel.
        if self._fake_atem is not None:
            self._fake_atem.remove_program_changed_callback(
                self._atem_dispatcher.on_program_changed
            )
            self._fake_atem.remove_program_changed_callback(
                self._right_panel.set_atem_program
            )
            self._fake_atem = None

        if is_fake_atem_mode(sim_active=_sim.is_active()):
            from adapters.fake_atem import FakeATEM
            # Fake mode owns the ATEM surface: drop any stale monitor
            # reference so atem_operational() gates on the FakeATEM alone.
            self._atem_monitor = None
            self._fake_atem = FakeATEM()
            self._fake_atem.connect()
            self._fake_atem.add_program_changed_callback(
                self._atem_dispatcher.on_program_changed
            )
            self._fake_atem.add_program_changed_callback(
                self._right_panel.set_atem_program
            )
            self._on_atem_state_changed(ATEMState.CONNECTED)
            import os as _os
            logger.info("[DEMO] FakeATEM selected (profile=%s sim=%s)",
                        _os.environ.get("KHPTZ_PROFILE", "production"), _sim.is_active())
            return

        # Keep the manual-command write adapter pointed at the current IP. It is
        # created once at startup, so without this it keeps trying the old IP
        # after the operator edits the ATEM IP in Settings and clicks Reconnect.
        if self._atem_write_adapter is not None and self._atem_write_adapter.ip != ATEM.ip:
            self._atem_write_adapter.set_ip(ATEM.ip)

        self._atem_monitor = ATEMMonitor(ATEM.ip, parent=self)
        for signal, slot in self._atem_monitor_signal_bindings(self._atem_monitor):
            signal.connect(slot)
        self._atem_monitor.start()

    def _on_atem_state_changed(self, state) -> None:
        sender = self.sender()
        if sender is not None and sender is not self._atem_monitor:
            return
        if state != ATEMState.CONNECTED:
            self._atem_verified_monitor = None
        if state is ATEMState.DISCONNECTED:
            if self._atem_state is not ATEMState.DISCONNECTED:
                self._atem_disconnected_at = time.monotonic()
        else:
            self._atem_disconnected_at = None
        self._atem_state = state
        self._atem_dispatcher.on_atem_state_changed(state)
        self._right_panel.set_atem_state(state)
        self.atem_state_changed.emit(state)
        self._update_atem_button(state)

    def _on_atem_action(self, action: str) -> None:
        if action == "comments_home":
            self._bus.emit(EventType.CAMERA_HOME, camera=2)
        elif action == "platform_home":
            self._bus.emit(EventType.SEAT_SELECTED, seat_number=1, camera=1, name="")
        elif action == "pip_on":
            self._pip_active = True
            self._notify_pip_state(True)
            # PiP activo: cámara principal retrocede a plano abierto (home mecánico)
            self._bus.emit(EventType.CAMERA_HOME, camera=1)
        elif action == "pip_off":
            self._pip_active = False
            self._notify_pip_state(False)
            # PiP desactivado: cámara principal vuelve a plano cerrado (sede 1)
            self._bus.emit(EventType.SEAT_SELECTED, seat_number=1, camera=1, name="")

    def _build_pip_nudge_service(self):
        """Construye el PiPNudgeService para el nudge de PiP.

        Siempre devuelve un servicio válido (nunca None): si config.yaml no está
        disponible o no tiene la sección pip_nudge, usa valores por defecto (0 = sin
        movimiento) para que la UI del panel ATEM pueda configurarlo sin reiniciar.
        """
        from application.pip_nudge_service import PiPNudgeService
        from config.settings import PiPNudgeSettings

        nudge_cfg = PiPNudgeSettings()   # defaults: pan_speed=0, duration_ms=0
        camera_id = "cam1"
        try:
            from config.effective import load_effective_config as load_config
            from config.registry import CameraRegistry
            from runtime.path_resolver import RuntimePathResolver

            resolver = RuntimePathResolver()
            settings = load_config(resolver.config_dir / "config.yaml")
            nudge_cfg = settings.atem.pip_nudge
            registry = CameraRegistry(settings.cameras)
            target_cam = registry.by_role(nudge_cfg.camera_role)
            cam_idx = next(
                (i + 1 for i, c in enumerate(settings.cameras) if c.id == target_cam.id),
                1,
            )
            camera_id = f"cam{cam_idx}"
        except Exception as exc:
            logger.debug("[PiPNudge] usando defaults (config no cargada: %s)", exc)

        return PiPNudgeService(
            camera_port=self._camera_port,
            camera_id=camera_id,
            settings=nudge_cfg,
            session_provider=lambda: self.session_active,
        )

    def _atem_monitor_is_healthy(self) -> bool:
        if self._atem_monitor is None:
            return True  # FakeATEM / no-ATEM path: never needs restart
        elapsed = None
        if self._atem_disconnected_at is not None:
            elapsed = time.monotonic() - self._atem_disconnected_at
        return is_atem_supervisor_healthy(
            is_running=self._atem_monitor.isRunning(),
            restart_pending=self._atem_restart_pending,
            state=self._atem_state,
            disconnected_elapsed_s=elapsed,
        )

    def _do_restart_atem_monitor(self):
        # Ejecutado en el hilo principal de Qt (vía QTimer.singleShot).
        if self._shutting_down:
            return
        if self._atem_restart_pending:
            return

        self._atem_restart_pending = True
        self._stop_and_replace_atem_monitor()

    def _stop_and_replace_atem_monitor(self):
        if self._shutting_down:
            self._atem_restart_pending = False
            return

        old_monitor = self._atem_monitor
        if old_monitor is None:
            self._atem_restart_pending = False
            # No monitor yet: the restart path doubles as the start path when
            # an ATEM is configured at runtime (first-time setup from
            # Settings, Scan/Reconnect buttons). Demo/sim is excluded — the
            # FakeATEM owns the surface and replacing it here would orphan
            # the demo panel's reference.
            if self._fake_atem is None and self._atem_is_configured():
                self._atem_dispatcher.mark_reconnecting()
                self._start_atem_monitor()
                logger.info("ATEMMonitor started after runtime configuration")
            return

        self._disconnect_atem_monitor_signals(old_monitor)
        if old_monitor.isRunning():
            old_monitor.finished.connect(
                lambda _old=old_monitor: self._finish_atem_monitor_restart(_old)
            )
            old_monitor.requestInterruption()
            return

        self._finish_atem_monitor_restart(old_monitor)

    def _finish_atem_monitor_restart(self, old_monitor):
        if self._shutting_down:
            self._atem_restart_pending = False
            return

        if old_monitor is not self._atem_monitor:
            old_monitor.deleteLater()
            return

        old_monitor.deleteLater()
        self._atem_dispatcher.mark_reconnecting()
        self._start_atem_monitor()
        self._atem_restart_pending = False
        logger.info("ATEMMonitor reiniciado por el supervisor")

    def _atem_monitor_signal_bindings(self, monitor) -> list:
        """Single source of truth for the (signal, slot) pairs wired to an
        ATEMMonitor. Used by both _start_atem_monitor (connect) and
        _disconnect_atem_monitor_signals (disconnect) so the two lists can never
        drift out of sync — previously the pip_nudge_svc binding was connected
        but not listed for disconnect.
        """
        bindings = [
            (monitor.program_verified, self._on_atem_program_verified),
            (monitor.program_changed, self._atem_dispatcher.on_program_changed),
            (monitor.program_changed, self._right_panel.set_atem_program),
            (monitor.program_changed, self._cache_atem_program),
            (monitor.state_changed,   self._on_atem_state_changed),
            (monitor.input_names_ready, self._right_panel.set_atem_input_names),
        ]
        if hasattr(self._atem_panel, "update_input_names"):
            bindings.append((monitor.input_names_ready, self._atem_panel.update_input_names))
        if hasattr(self._atem_panel, "on_program_changed"):
            bindings.append((monitor.program_changed, self._atem_panel.on_program_changed))
        bindings += [
            (monitor.pip_changed, self._atem_dispatcher.on_pip_changed),
            (monitor.pip_changed, self._right_panel.set_pip_state),
            (monitor.pip_changed, self._on_pip_state_changed),
            (monitor.pip_changed, self._pip_nudge_svc.on_pip_changed),
        ]
        return bindings

    def _disconnect_atem_monitor_signals(self, monitor) -> None:
        if monitor is None:
            return
        for signal, slot in self._atem_monitor_signal_bindings(monitor):
            try:
                signal.disconnect(slot)
            except TypeError:
                logger.debug("ATEM signal already disconnected from slot %s", slot)

    def _record_activity(self):
        self._last_activity = time.monotonic()

    _INACTIVITY_TIMEOUT = 2 * 3600  # 2 horas en segundos

    def _check_inactivity(self):
        if not self.session_active:
            return
        if time.monotonic() - self._last_activity < self._INACTIVITY_TIMEOUT:
            return
        logger.info("Auto power-off: 2 horas sin actividad")
        self._session.shutdown("inactivity")

    def _on_screen_turned_off(self):
        """Triggered by ScreenMonitor (DPMS) or GpioMonitor (physical button).

        Only acts when a session is active. Wakes the screen, shows a 30-second
        countdown dialog, and powers off cameras if the operator confirms (or time runs out).
        Closing the dialog with X is treated as No — session continues, screen stays on.
        """
        if self._shutting_down or self._screen_dialog_active:
            return
        if not self.session_active:
            return

        self._screen_dialog_active = True
        try:
            ScreenMonitor.wake()
            dialog = ScreenOffDialog(self)
            accepted = dialog.exec_() == ScreenOffDialog.Accepted
            if accepted:
                self._session.shutdown("screen_off")
                generation = self._session._session_generation
                QTimer.singleShot(1500, lambda: self._sleep_screen_after_session_end(generation))
            # Rejected or X: screen stays on, session continues
        finally:
            self._screen_dialog_active = False

    def _sleep_screen_after_session_end(self, generation: int) -> None:
        """Discard delayed DPMS work if another session or app close began."""
        if (self._shutting_down or self.session_active
                or self._session._session_generation != generation):
            return
        ScreenMonitor.sleep()

    def _ask_shutdown_intent(self) -> "ShutdownIntent":
        """Show a shutdown dialog and return the operator's explicit choice.

        Thin delegate to ui.shutdown_intent_dialog. Kept as a method so tests
        can patch it without showing a dialog.
        """
        from ui.shutdown_intent_dialog import ask_shutdown_intent
        return ask_shutdown_intent(self)

    def closeEvent(self, event):
        from domain.shutdown_intent import ShutdownIntent

        intent = self._ask_shutdown_intent()
        if intent == ShutdownIntent.CANCEL:
            # Si había un restart-as-admin pendiente, cancelarlo también:
            # borrar el flag de disco y limpiar el estado interno.
            if self._pending_admin_restart:
                try:
                    from runtime.path_resolver import RuntimePathResolver
                    flag = RuntimePathResolver().admin_login_flag
                    if flag.exists():
                        flag.unlink()
                        logger.info("[SHUTDOWN] admin restart cancelled — flag removed")
                except OSError as exc:
                    logger.warning("No se pudo borrar admin_login.flag: %s", exc)
                self._pending_admin_restart = None
            event.ignore()
            return

        from ui.runtime_restart import prepare_runtime_restart
        if not prepare_runtime_restart(self):
            event.ignore()
            return

        # Marcar cierre antes de parar el supervisor para que cualquier callback
        # pendiente de QTimer.singleShot (_restart_atem_monitor, _session_home)
        # vea el flag y salga sin enviar comandos.
        self._shutting_down = True
        logger.info("[SHUTDOWN] intent=%s", intent.value)
        logger.info("[SHUTDOWN] stopping inactivity timer")
        self._inactivity_timer.stop()
        if self._screen_monitor is not None:
            logger.info("[SHUTDOWN] stopping screen monitor")
            self._screen_monitor.requestInterruption()
            self._screen_monitor.wait(3000)
        if self._gpio_monitor is not None:
            logger.info("[SHUTDOWN] stopping GPIO monitor")
            self._gpio_monitor.requestInterruption()
            self._gpio_monitor.wait(3000)
        logger.info("[SHUTDOWN] stopping supervisor")
        self._supervisor.stop()
        if self.session_active:
            logger.info("[SHUTDOWN] ending active session on app close")
            self._session.shutdown(
                "app_close", power_off=(intent == ShutdownIntent.EXIT_AND_POWER_OFF_CAMERAS),
            )
        logger.info("[SHUTDOWN] stopping event bus")
        self._bus.stop()
        if intent == ShutdownIntent.EXIT_AND_POWER_OFF_CAMERAS:
            logger.info("[SHUTDOWN] sending camera standby (operator requested power-off)")
            # Standby uses the current worker session, before terminal retirement.
            self._camera_port.standby("cam1")
            self._camera_port.standby("cam2")
        else:
            logger.info("[SHUTDOWN] skipping camera standby (operator chose keep cameras on)")

        logger.info("[SHUTDOWN] stopping camera workers")
        self._cameras.stop_all()
        if self._atem_monitor is not None:
            logger.info("[SHUTDOWN] interrupting ATEM monitor")
            self._atem_monitor.requestInterruption()
            self._atem_monitor.wait(2000)
        elif self._fake_atem is not None:
            logger.info("[SHUTDOWN] disconnecting FakeATEM")
            self._fake_atem.disconnect()
        if self._atem_write_adapter is not None:
            logger.info("[SHUTDOWN] disconnecting ATEM write adapter")
            self._atem_write_adapter.disconnect()

        logger.info("[SHUTDOWN] complete")
        event.accept()

        # Si el cierre fue iniciado por "Restart as admin", lanzar el nuevo
        # proceso AHORA — después de que el hardware esté parado y el diálogo
        # de shutdown haya sido aceptado por el operador.
        if self._pending_admin_restart:
            from ui.runtime_restart import launch_pending_restart
            logger.info("[SHUTDOWN] launching restart process")
            try:
                launch_pending_restart(self)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[SHUTDOWN] admin-restart launch failed: %s", exc)
            self._pending_admin_restart = None

    @pyqtSlot()
    def _update_focus_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        self._right_panel.set_focus_mode(self._cameras.focus_mode[cam_key])

    def _update_exposure_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        self._right_panel.set_exposure_level(self._cameras.exposure_level[cam_key])

    def _update_controls_visibility(self):
        from ui.camera_controls_visibility import update_camera_controls_visibility
        update_camera_controls_visibility(self)

    @pyqtSlot()
    def _update_backlight_ui(self):
        cam_key = 1 if self.Cam1.isChecked() else 2
        if self._cameras.backlight_on[cam_key]:
            self.BtnBacklight.setText('Backlight\nON')
            self.BtnBacklight.setStyleSheet(self._backlight_style_on)
        else:
            self.BtnBacklight.setText('Backlight\nOFF')
            self.BtnBacklight.setStyleSheet(self._backlight_style_off)
        self._cam_indicator.set_mode('platform' if cam_key == 1 else 'comments')

    @pyqtSlot(int)
    def _set_zoom_feedback(self, pct: int):
        """Actualiza el slider desde el feedback de red sin disparar ZoomAbsolute."""
        self._zoom_feedback = True
        self.ZoomSlider.setValue(pct)
        self._zoom_feedback = False
