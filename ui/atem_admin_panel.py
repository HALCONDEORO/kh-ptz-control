#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/atem_admin_panel.py — Admin/support ATEM control panel (#554)
#
# AtemAdminPanel is the production admin panel — NOT the demo simulator panel.
# It is only shown in TECHNICIAN context and only when ATEM is installed+enabled.
#
# CUT/AUTO buttons are disabled for non-TECHNICIAN roles with tooltip explanation.
# Status text is never color-only.
# Panel must only be instantiated when ATEM is configured.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from domain.atem_constants import ATEM_INPUT_LABELS_LIST as _INPUT_LABELS_LIST

try:
    from PyQt5.QtCore import QTimer, Qt
    from PyQt5.QtWidgets import (
        QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout,
    )
    _QT_AVAILABLE = True
    _QFrameBase = QFrame
except ImportError:  # pragma: no cover
    _QT_AVAILABLE = False
    _QFrameBase = object  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from application.atem_command_service import AtemCommandService
    from application.atem_diagnostics_service import AtemDiagnosticsService
    from application.pip_nudge_service import PiPNudgeService
    from domain.call_set_policy import OperatingMode

logger = logging.getLogger(__name__)

# ── Styles ─────────────────────────────────────────────────────────────────────

_HEADER_STYLE = (
    "QLabel { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
    " stop:0 #2E5229, stop:1 #1A3318);"
    " color: white; font: 700 13px 'Inter Tight', 'Segoe UI', sans-serif;"
    " padding: 5px 10px; border-radius: 8px; }"
)
_FRAME_STYLE = (
    "AtemAdminPanel { background: #FAFAF9; border: 1px solid #E4E7E2; border-radius: 10px; }"
)
_CLOSE_BTN_STYLE = (
    "QPushButton { background: white; color: #333333; border: 1px solid #DCDEDB;"
    " border-radius: 6px; font: 700 13px 'Inter Tight', 'Segoe UI'; padding: 0; }"
    "QPushButton:hover { background: #FCECEA; border-color: rgba(192,20,31,0.40);"
    " color: #C0141F; }"
    "QPushButton:pressed { background: #F7D9D6; }"
)
_STATUS_STYLE = "QLabel { color: #666666; font: 11px 'Inter Tight', 'Segoe UI', sans-serif; }"
_SECTION_STYLE = (
    "QLabel { color: #555555; font: 700 10px 'Inter Tight', 'Segoe UI', sans-serif;"
    " margin-top: 4px; letter-spacing: 0.08em; }"
)
_BTN_NORMAL = (
    "QPushButton { background: white; color: #333333; border: 1px solid #DCDEDB;"
    " border-radius: 6px; font: 600 12px 'Inter Tight', 'Segoe UI'; padding: 4px 8px; }"
    "QPushButton:hover { background: #F6F7F5; border-color: #C8CAC6; color: #1A3318; }"
    "QPushButton:disabled { color: #999999; background: #F4F5F3; border-color: #E0E2DE; }"
)
_BTN_LIVE = (
    "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
    " stop:0 #2E5229, stop:1 #1A3318);"
    " color: white; border: none; border-radius: 6px;"
    " font: 700 12px 'Inter Tight', 'Segoe UI'; padding: 4px 10px; }"
    "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
    " stop:0 #3a6633, stop:1 #223d20); }"
    "QPushButton:disabled { color: #999999; background: #E0E2DE; }"
)
# Botón que está en programa AHORA — rojo vivo (igual que el botón rojo físico del ATEM)
_BTN_PROGRAM = (
    "QPushButton { background: #FCECEA; color: #C0141F; border: 2px solid rgba(192,20,31,0.40);"
    " border-radius: 6px; font: 700 12px 'Inter Tight', 'Segoe UI'; padding: 4px 8px; }"
)
_RESULT_STYLE = (
    "QLabel { color: #1A3318; font: 10px 'Consolas', 'Courier New', monospace;"
    " background: #EAF6EE; border: 1px solid rgba(27,127,62,0.30);"
    " border-radius: 6px; padding: 3px 5px; }"
)


class AtemAdminPanel(_QFrameBase):  # type: ignore[valid-type]
    """Admin/support ATEM control panel.

    Exposes Program/Preview status and manual commands for TECHNICIAN role.
    CUT/AUTO are disabled with explanatory tooltip when role is insufficient.

    Never show in production to normal operators.
    Only instantiate when ATEM is installed+enabled in config.
    """

    _REFRESH_MS = 1000

    _INPUT_LABELS = _INPUT_LABELS_LIST
    _PREVIEW_COLS = 5  # botones por fila en la cuadrícula de inputs

    def __init__(
        self,
        diagnostics_svc: "AtemDiagnosticsService",
        command_svc: "AtemCommandService",
        role_provider: "Optional[Callable[[], OperatingMode]]" = None,
        pip_automation_provider: "Optional[Callable[[], bool]]" = None,
        pip_automation_setter: "Optional[Callable[[bool], None]]" = None,
        atem_configured_provider: "Optional[Callable[[], bool]]" = None,
        pip_nudge_svc: "Optional[PiPNudgeService]" = None,
        pip_set_fn: "Optional[Callable[[bool], None]]" = None,
        pip_save_fn: "Optional[Callable[[int, str, int], None]]" = None,
        on_close: "Optional[Callable[[], None]]" = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._diag = diagnostics_svc
        self._cmd = command_svc
        self._on_close = on_close
        self._role_fn = role_provider
        self._pip_automation_provider = pip_automation_provider
        self._pip_automation_setter = pip_automation_setter
        self._atem_configured_provider = atem_configured_provider
        self._pip_nudge_svc = pip_nudge_svc
        self._pip_set_fn = pip_set_fn
        self._pip_save_fn = pip_save_fn

        self.setStyleSheet(_FRAME_STYLE)
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        header = QLabel("ATEM — ADMIN / SUPPORT")
        header.setStyleSheet(_HEADER_STYLE)
        header.setAlignment(Qt.AlignCenter)
        header_row.addWidget(header, stretch=1)

        self._btn_close = QPushButton("✕")
        self._btn_close.setFixedSize(28, 28)
        self._btn_close.setToolTip("Close panel")
        self._btn_close.setStyleSheet(_CLOSE_BTN_STYLE)
        self._btn_close.clicked.connect(self._handle_close)
        header_row.addWidget(self._btn_close)
        root.addLayout(header_row)

        # ── Status ────────────────────────────────────────────────────────────
        self._lbl_state = QLabel("State: checking…")
        self._lbl_state.setStyleSheet(_STATUS_STYLE)
        root.addWidget(self._lbl_state)

        self._lbl_program = QLabel("Program: —")
        self._lbl_program.setStyleSheet(_STATUS_STYLE)
        root.addWidget(self._lbl_program)

        self._lbl_preview = QLabel("Preview: —")
        self._lbl_preview.setStyleSheet(_STATUS_STYLE)
        root.addWidget(self._lbl_preview)

        self._lbl_role = QLabel("Role: —")
        self._lbl_role.setStyleSheet(_STATUS_STYLE)
        root.addWidget(self._lbl_role)

        # ── Set Preview (dinámico — se reconstruye con los inputs reales del ATEM) ──
        prev_lbl = QLabel("INPUTS DEL ATEM")
        prev_lbl.setStyleSheet(_SECTION_STYLE)
        root.addWidget(prev_lbl)

        # Contenedor reconstruible — se llena con fallback hardcodeado y se reemplaza
        # con los inputs reales cuando input_names_ready llega del ATEMMonitor
        self._prev_buttons_widget = QFrame()
        self._prev_buttons_layout = QGridLayout(self._prev_buttons_widget)
        self._prev_buttons_layout.setSpacing(3)
        self._prev_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self._preview_btns: dict[int, QPushButton] = {}
        self._current_program: "int | None" = None

        # Arranca con los botones fallback — se reemplazan al conectar el ATEM real
        self._build_fallback_buttons()

        root.addWidget(self._prev_buttons_widget)

        # ── Live switch ───────────────────────────────────────────────────────
        live_lbl = QLabel("LIVE SWITCH (TECHNICIAN ONLY)")
        live_lbl.setStyleSheet(_SECTION_STYLE)
        root.addWidget(live_lbl)

        live_row = QHBoxLayout()
        live_row.setSpacing(6)

        self._btn_cut = QPushButton("CUT")
        self._btn_cut.setStyleSheet(_BTN_LIVE)
        self._btn_cut.clicked.connect(self._on_cut)
        live_row.addWidget(self._btn_cut)

        self._btn_auto = QPushButton("AUTO")
        self._btn_auto.setStyleSheet(_BTN_LIVE)
        self._btn_auto.clicked.connect(self._on_auto)
        live_row.addWidget(self._btn_auto)

        auto_note = QLabel("Uses current ATEM transition settings")
        auto_note.setStyleSheet(_STATUS_STYLE)
        live_row.addWidget(auto_note)
        root.addLayout(live_row)

        # ── PiP control (ON/OFF + estado) ────────────────────────────────────
        pip_ctrl_lbl = QLabel("PIP")
        pip_ctrl_lbl.setStyleSheet(_SECTION_STYLE)
        root.addWidget(pip_ctrl_lbl)

        pip_ctrl_row = QHBoxLayout()
        pip_ctrl_row.setSpacing(6)

        btn_pip_on = QPushButton("PiP ON")
        btn_pip_on.setStyleSheet(_BTN_LIVE)
        btn_pip_on.clicked.connect(lambda: self._pip_set(True))
        pip_ctrl_row.addWidget(btn_pip_on)

        btn_pip_off = QPushButton("PiP OFF")
        btn_pip_off.setStyleSheet(_BTN_NORMAL)
        btn_pip_off.clicked.connect(lambda: self._pip_set(False))
        pip_ctrl_row.addWidget(btn_pip_off)

        self._lbl_pip_state = QLabel("PiP: ○  inactivo")
        self._lbl_pip_state.setStyleSheet(_STATUS_STYLE)
        pip_ctrl_row.addWidget(self._lbl_pip_state)

        root.addLayout(pip_ctrl_row)

        # ── PiP automation toggle ─────────────────────────────────────────────
        if self._pip_automation_provider is not None:
            pip_lbl = QLabel("PIP AUTOMATION")
            pip_lbl.setStyleSheet(_SECTION_STYLE)
            root.addWidget(pip_lbl)

            pip_row = QHBoxLayout()
            pip_row.setSpacing(6)

            self._btn_pip_enable = QPushButton("Enable PiP Auto")
            self._btn_pip_enable.setStyleSheet(_BTN_NORMAL)
            self._btn_pip_enable.clicked.connect(lambda: self._set_pip_automation(True))
            pip_row.addWidget(self._btn_pip_enable)

            self._btn_pip_disable = QPushButton("Disable PiP Auto")
            self._btn_pip_disable.setStyleSheet(_BTN_NORMAL)
            self._btn_pip_disable.clicked.connect(lambda: self._set_pip_automation(False))
            pip_row.addWidget(self._btn_pip_disable)

            self._lbl_pip_status = QLabel("PiP Auto: —")
            self._lbl_pip_status.setStyleSheet(_STATUS_STYLE)
            pip_row.addWidget(self._lbl_pip_status)

            root.addLayout(pip_row)
        else:
            self._btn_pip_enable = None   # type: ignore[assignment]
            self._btn_pip_disable = None  # type: ignore[assignment]
            self._lbl_pip_status = None   # type: ignore[assignment]

        # ── PiP nudge settings ────────────────────────────────────────────────
        nudge_lbl = QLabel("PIP NUDGE (cámara platform)")
        nudge_lbl.setStyleSheet(_SECTION_STYLE)
        root.addWidget(nudge_lbl)

        nudge_row1 = QHBoxLayout()
        nudge_row1.setSpacing(4)

        nudge_row1.addWidget(QLabel("Dir:"))
        self._nudge_dir = QComboBox()
        self._nudge_dir.addItems(["right", "left"])
        if self._pip_nudge_svc is not None:
            self._nudge_dir.setCurrentIndex(
                1 if self._pip_nudge_svc._cfg.direction == "left" else 0
            )
        nudge_row1.addWidget(self._nudge_dir)

        nudge_row1.addWidget(QLabel("Speed (0–24):"))
        self._nudge_speed = QSpinBox()
        self._nudge_speed.setRange(0, 24)
        self._nudge_speed.setValue(self._pip_nudge_svc._cfg.pan_speed if self._pip_nudge_svc else 0)
        nudge_row1.addWidget(self._nudge_speed)

        nudge_row1.addWidget(QLabel("ms (0–5000):"))
        self._nudge_duration = QSpinBox()
        self._nudge_duration.setRange(0, 5000)
        self._nudge_duration.setSingleStep(50)
        self._nudge_duration.setValue(self._pip_nudge_svc._cfg.duration_ms if self._pip_nudge_svc else 0)
        nudge_row1.addWidget(self._nudge_duration)

        root.addLayout(nudge_row1)

        self._lbl_nudge_status = QLabel(
            self._pip_nudge_svc.describe() if self._pip_nudge_svc else "sin servicio"
        )
        self._lbl_nudge_status.setStyleSheet(_STATUS_STYLE)
        root.addWidget(self._lbl_nudge_status)

        if self._pip_nudge_svc is not None:
            self._nudge_speed.valueChanged.connect(self._on_nudge_changed)
            self._nudge_duration.valueChanged.connect(self._on_nudge_changed)
            self._nudge_dir.currentTextChanged.connect(self._on_nudge_changed)

        if self._pip_save_fn is not None:
            btn_save_nudge = QPushButton("Guardar en config.yaml")
            btn_save_nudge.setStyleSheet(_BTN_NORMAL)
            btn_save_nudge.clicked.connect(self._on_save_nudge)
            root.addWidget(btn_save_nudge)

        # ── Last command result ───────────────────────────────────────────────
        self._lbl_result = QLabel("Last command: —")
        self._lbl_result.setStyleSheet(_RESULT_STYLE)
        self._lbl_result.setWordWrap(True)
        root.addWidget(self._lbl_result)

        root.addStretch()

        # ── Polling ───────────────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(self._REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    # ── Close ───────────────────────────────────────────────────────────────────

    def _handle_close(self) -> None:
        """Hide the panel. Always works, even when the ATEM toggle button is
        disabled because the switcher is unreachable."""
        if self._on_close is not None:
            self._on_close()
        else:
            self.hide()

    # ── PiP automation control ────────────────────────────────────────────────

    def set_pip_state(self, active: bool) -> None:
        """Actualiza el indicador de estado PiP (llamado desde MainWindow)."""
        if active:
            self._lbl_pip_state.setText("PiP: ●  ACTIVO")
            self._lbl_pip_state.setStyleSheet(
                "QLabel { color: #FF6600; font: bold 11px 'Segoe UI', sans-serif; }"
            )
        else:
            self._lbl_pip_state.setText("PiP: ○  inactivo")
            self._lbl_pip_state.setStyleSheet(_STATUS_STYLE)

    def _pip_set(self, state: bool) -> None:
        if self._pip_set_fn is not None:
            self._pip_set_fn(state)

    def _on_save_nudge(self) -> None:
        if self._pip_save_fn is None:
            return
        self._pip_save_fn(
            self._nudge_speed.value(),
            self._nudge_dir.currentText(),
            self._nudge_duration.value(),
        )

    def _on_nudge_changed(self) -> None:
        if self._pip_nudge_svc is None:
            return
        self._pip_nudge_svc.update(
            pan_speed=self._nudge_speed.value(),
            direction=self._nudge_dir.currentText(),
            duration_ms=self._nudge_duration.value(),
        )
        self._lbl_nudge_status.setText(self._pip_nudge_svc.describe())

    def _atem_is_configured(self) -> bool:
        """True when an ATEM IP is configured (or no provider was supplied).

        Without a configured switcher, PiP automation has nothing to drive, so
        the toggle is disabled. Defaults to True when no provider is given to
        preserve existing behaviour (demo/tests build the panel without one).
        """
        if self._atem_configured_provider is None:
            return True
        try:
            return bool(self._atem_configured_provider())
        except Exception:
            return True

    def _set_pip_automation(self, enabled: bool) -> None:
        if not self._atem_is_configured():
            return
        if self._pip_automation_setter is not None:
            self._pip_automation_setter(enabled)
        self._refresh_pip_status()

    def _refresh_pip_status(self) -> None:
        if self._lbl_pip_status is None or self._pip_automation_provider is None:
            return
        configured = self._atem_is_configured()
        if not configured:
            self._lbl_pip_status.setText("PiP Auto: no ATEM")
            _tip = "Configure the ATEM IP first"
            if self._btn_pip_enable is not None:
                self._btn_pip_enable.setEnabled(False)
                self._btn_pip_enable.setToolTip(_tip)
            if self._btn_pip_disable is not None:
                self._btn_pip_disable.setEnabled(False)
                self._btn_pip_disable.setToolTip(_tip)
            return
        enabled = self._pip_automation_provider()
        self._lbl_pip_status.setText("PiP Auto: ON" if enabled else "PiP Auto: OFF")
        if self._btn_pip_enable is not None:
            self._btn_pip_enable.setEnabled(not enabled)
            self._btn_pip_enable.setToolTip("")
        if self._btn_pip_disable is not None:
            self._btn_pip_disable.setEnabled(enabled)
            self._btn_pip_disable.setToolTip("")

    # ── Input buttons helpers ──────────────────────────────────────────────────

    def _build_fallback_buttons(self) -> None:
        """Construye los botones con los labels hardcodeados de atem_constants.

        Se usa como estado inicial y como fallback si el ATEM no envía inputs.
        """
        if not _QT_AVAILABLE:
            return
        self._clear_buttons()
        for idx, (inp, label) in enumerate(self._INPUT_LABELS):
            btn = QPushButton(f"{inp}: {label}")
            btn.setStyleSheet(_BTN_NORMAL)
            btn.clicked.connect(self._make_preview_fn(inp))
            row, col = divmod(idx, self._PREVIEW_COLS)
            self._prev_buttons_layout.addWidget(btn, row, col)
            self._preview_btns[inp] = btn

    def _clear_buttons(self) -> None:
        """Elimina todos los widgets del contenedor de botones."""
        while self._prev_buttons_layout.count():
            item = self._prev_buttons_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._preview_btns.clear()

    # ── Input name updates from real ATEM ─────────────────────────────────────

    def update_input_names(self, names: dict) -> None:
        """Reconstruye los botones de inputs con los nombres reales del ATEM.

        Se llama cuando input_names_ready llega del ATEMMonitor (al conectar).
        Reemplaza completamente la cuadrícula — soporta cualquier número de inputs.
        Si ya había un input en programa, lo re-ilumina tras reconstruir.
        """
        # Si no hay inputs, volver al fallback hardcodeado
        if not names:
            self._build_fallback_buttons()
            return

        if not _QT_AVAILABLE:
            return

        self._clear_buttons()

        # Construir un botón por cada input recibido del ATEM, en orden
        for idx, input_id in enumerate(sorted(names.keys())):
            name = names[input_id]
            btn = QPushButton(f"{input_id}: {name}")
            btn.setStyleSheet(_BTN_NORMAL)
            btn.clicked.connect(self._make_preview_fn(input_id))
            row, col = divmod(idx, self._PREVIEW_COLS)
            self._prev_buttons_layout.addWidget(btn, row, col)
            self._preview_btns[input_id] = btn

        # Restaurar iluminación si ya se sabe qué input está en programa
        if self._current_program is not None:
            btn = self._preview_btns.get(self._current_program)
            if btn is not None:
                btn.setStyleSheet(_BTN_PROGRAM)

        logger.info("[ATEM] %d inputs recibidos del switcher: %s",
                    len(names), sorted(names.keys()))

    def on_program_changed(self, input_num: int) -> None:
        """Ilumina el botón del input activo cuando se pulsa un botón en el ATEM.

        Apaga el botón anterior (si era distinto) y enciende el nuevo en rojo vivo.
        Funciona aunque los botones todavía no existan (se re-aplica en update_input_names).
        """
        if self._current_program is not None and self._current_program != input_num:
            prev_btn = self._preview_btns.get(self._current_program)
            if prev_btn is not None:
                prev_btn.setStyleSheet(_BTN_NORMAL)
        self._current_program = input_num
        btn = self._preview_btns.get(input_num)
        if btn is not None:
            btn.setStyleSheet(_BTN_PROGRAM)
        logger.debug("[ATEM] programa → input %d", input_num)

    # ── Role helpers ──────────────────────────────────────────────────────────

    def _current_role(self) -> "OperatingMode":
        from domain.call_set_policy import OperatingMode
        if self._role_fn is not None:
            return self._role_fn()
        return OperatingMode.CAMERA_OPERATOR

    def _is_technician(self) -> bool:
        # Delegates to the single domain rule so the button-enabling logic here
        # can never diverge from the command guard in AtemCommandService.
        # Administrator (SYSTEM_ADMIN) has full access including live switching;
        # TECHNICIAN keeps it for backward compatibility.
        from domain.atem_policy import can_live_switch
        return can_live_switch(self._current_role())

    # ── Button handlers ───────────────────────────────────────────────────────

    def _make_preview_fn(self, inp: int):
        def handler():
            result = self._cmd.set_preview(inp, role=self._current_role())
            self._show(result, f"set_preview({inp})")
            self.refresh()
        return handler

    def _on_cut(self) -> None:
        result = self._cmd.cut(role=self._current_role())
        self._show(result, "cut")
        self.refresh()

    def _on_auto(self) -> None:
        result = self._cmd.auto(role=self._current_role())
        self._show(result, "auto")
        self.refresh()

    def _show(self, result, label: str) -> None:
        if result.ok:
            self._lbl_result.setText(f"OK  {label}")
        else:
            self._lbl_result.setText(f"ERR {label}: {result.message}")

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        status_result = self._diag.read_status()
        data = status_result.data or {}
        connected = data.get("connected", False)
        if connected:
            state_text = "State: Connected"
        else:
            state_text = f"State: Disconnected — {status_result.message}"
        self._lbl_state.setText(state_text)

        prog = data.get("program_input")
        prev = data.get("preview_input")
        self._lbl_program.setText(f"Program: {prog if prog is not None else 'unknown'}")
        self._lbl_preview.setText(f"Preview: {prev if prev is not None else 'unknown'}")

        role = self._current_role()
        self._lbl_role.setText(f"Role: {role.value}")

        tech = self._is_technician()
        tip = "" if tech else "Requires technician role to perform live switching"
        self._btn_cut.setEnabled(tech)
        self._btn_auto.setEnabled(tech)
        self._btn_cut.setToolTip(tip)
        self._btn_auto.setToolTip(tip)

        self._refresh_pip_status()
