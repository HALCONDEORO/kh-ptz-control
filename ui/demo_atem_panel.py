#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/demo_atem_panel.py — Virtual ATEM control panel for demo/simulation mode
#
# WARNING: THIS PANEL MUST NEVER BE SHOWN IN PRODUCTION MODE.
# It only makes sense when the application is running with a FakeATEM adapter.
# The caller (bootstrap / demo wiring) is responsible for only instantiating
# this widget when demo/simulation mode is active.

from __future__ import annotations

import datetime
import logging
from typing import ClassVar, TYPE_CHECKING

from domain.atem_constants import ATEM_INPUT_LABELS as _INPUT_LABELS, ATEM_INPUT_LABELS_LIST
from domain.atem_state import ATEMPiPState

try:
    from PyQt5.QtCore import QEvent, QTimer, Qt
    from PyQt5.QtWidgets import (
        QComboBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QSpinBox,
        QVBoxLayout,
        QWidget,
    )
    _QT_AVAILABLE = True
    _QWidgetBase = QWidget
except ImportError:  # pragma: no cover
    _QT_AVAILABLE = False
    _QWidgetBase = object  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from adapters.fake_atem import FakeATEM
    from adapters.atem_dispatcher import ATEMDispatcher
    from application.pip_nudge_service import PiPNudgeService

logger = logging.getLogger(__name__)


def _format_input_label(input_id: int | None) -> str:
    if input_id is None:
        return "None"
    label = _INPUT_LABELS.get(input_id, f"Input {input_id}")
    return f"{input_id} — {label}"


def _format_automation_state(
    armed: bool,
    log_only: bool,
    reconnect_guard: bool,
    pip_automation_enabled: bool = True,
) -> str:
    pip_suffix = "" if pip_automation_enabled else " | PiP OFF"
    if not armed:
        return f"DISARMED{pip_suffix}"
    if log_only:
        return f"LOG-ONLY{pip_suffix}"
    if reconnect_guard:
        return f"ARMED (reconnect guard){pip_suffix}"
    return f"ARMED{pip_suffix}"


# ── Styles ─────────────────────────────────────────────────────────────────────

_HEADER_STYLE = (
    "QLabel {"
    "  background-color: #F5A623;"
    "  color: #1A1A1A;"
    "  font: 700 15px 'Segoe UI', sans-serif;"
    "  padding: 8px 14px;"
    "  border-radius: 4px;"
    "}"
)

_WINDOW_STYLE = (
    "DemoAtemPanel {"
    "  background-color: #2A2A2A;"
    "}"
)

_STATUS_LABEL_STYLE = (
    "QLabel {"
    "  color: #E0E0E0;"
    "  font: 13px 'Segoe UI', sans-serif;"
    "  padding: 1px 0;"
    "}"
)

_SECTION_LABEL_STYLE = (
    "QLabel {"
    "  color: #AAAAAA;"
    "  font: 700 11px 'Segoe UI', sans-serif;"
    "  margin-top: 8px;"
    "  letter-spacing: 1px;"
    "}"
)

_DRY_RUN_STYLE = (
    "QLabel {"
    "  color: #F5A623;"
    "  font: 12px 'Courier New', monospace;"
    "  background-color: #1A1A1A;"
    "  border: 1px solid #444444;"
    "  border-radius: 3px;"
    "  padding: 5px 8px;"
    "}"
)

_BTN_BASE = (
    "QPushButton {"
    "  background-color: #3C3C3C;"
    "  color: #DDDDDD;"
    "  border: 1px solid #555555;"
    "  border-radius: 5px;"
    "  font: 13px 'Segoe UI', sans-serif;"
    "  padding: 7px 10px;"
    "  min-height: 32px;"
    "}"
    "QPushButton:hover { background-color: #505050; border-color: #888888; }"
    "QPushButton:pressed { background-color: #222222; }"
)

_BTN_SELECTED = (
    "QPushButton {"
    "  background-color: #B8560A;"
    "  color: #FFFFFF;"
    "  border: 2px solid #F5A623;"
    "  border-radius: 5px;"
    "  font: 700 13px 'Segoe UI', sans-serif;"
    "  padding: 7px 10px;"
    "  min-height: 32px;"
    "}"
)

_BTN_PREVIEW_SELECTED = (
    "QPushButton {"
    "  background-color: #0A5680;"
    "  color: #FFFFFF;"
    "  border: 2px solid #23A8E0;"
    "  border-radius: 5px;"
    "  font: 700 13px 'Segoe UI', sans-serif;"
    "  padding: 7px 10px;"
    "  min-height: 32px;"
    "}"
)

_BTN_CONTROL = (
    "QPushButton {"
    "  background-color: #3A3A5A;"
    "  color: #CCCCFF;"
    "  border: 1px solid #5555AA;"
    "  border-radius: 5px;"
    "  font: 13px 'Segoe UI', sans-serif;"
    "  padding: 6px 10px;"
    "  min-height: 30px;"
    "}"
    "QPushButton:hover { background-color: #505080; border-color: #8888CC; }"
    "QPushButton:pressed { background-color: #202040; }"
)

_BTN_SWITCH = (
    "QPushButton {"
    "  background-color: #5A3A3A;"
    "  color: #FFCCCC;"
    "  border: 1px solid #AA5555;"
    "  border-radius: 5px;"
    "  font: 700 14px 'Segoe UI', sans-serif;"
    "  padding: 8px 14px;"
    "  min-height: 34px;"
    "}"
    "QPushButton:hover { background-color: #805050; border-color: #CC8888; }"
    "QPushButton:pressed { background-color: #402020; }"
)

_BTN_CONN = (
    "QPushButton {"
    "  background-color: #3A5A3A;"
    "  color: #CCFFCC;"
    "  border: 1px solid #55AA55;"
    "  border-radius: 5px;"
    "  font: 13px 'Segoe UI', sans-serif;"
    "  padding: 6px 10px;"
    "  min-height: 30px;"
    "}"
    "QPushButton:hover { background-color: #508050; border-color: #88CC88; }"
    "QPushButton:pressed { background-color: #204020; }"
)

_RESULT_STYLE = (
    "QLabel {"
    "  color: #88FF88;"
    "  font: 12px 'Courier New', monospace;"
    "  background-color: #1A1A1A;"
    "  border: 1px solid #444444;"
    "  border-radius: 3px;"
    "  padding: 5px 8px;"
    "}"
)


class DemoAtemPanel(_QWidgetBase):  # type: ignore[valid-type]
    """
    Virtual ATEM control surface for demo/simulation mode.

    Shows Program bus (read-only highlight), Preview bus (interactive),
    CUT/AUTO transition buttons, connection controls and automation safety.

    WARNING: Must only be instantiated in demo/simulation mode with FakeATEM.
    """

    _REFRESH_INTERVAL_MS = 500

    _INPUT_BUTTONS: ClassVar[list] = [(inp, f"{inp}  {label}") for inp, label in ATEM_INPUT_LABELS_LIST]

    def __init__(
        self,
        fake_atem: "FakeATEM",
        dispatcher: "ATEMDispatcher",
        pip_nudge_svc: "PiPNudgeService | None" = None,
        pip_save_fn=None,
        parent=None,
    ) -> None:
        super().__init__(parent, Qt.Window)
        self._fake_atem = fake_atem
        self._dispatcher = dispatcher
        self._pip_nudge_svc = pip_nudge_svc
        self._pip_save_fn = pip_save_fn

        self.setWindowTitle("DEMO — Virtual ATEM")
        self.setStyleSheet(_WINDOW_STYLE)
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────────
        header = QLabel("DEMO — VIRTUAL ATEM")
        header.setStyleSheet(_HEADER_STYLE)
        header.setAlignment(Qt.AlignCenter)
        root.addWidget(header)

        # ── Status section ────────────────────────────────────────────────────
        self._lbl_state = QLabel("State: —")
        self._lbl_state.setStyleSheet(_STATUS_LABEL_STYLE)
        root.addWidget(self._lbl_state)

        self._lbl_program = QLabel("Program: —")
        self._lbl_program.setStyleSheet(_STATUS_LABEL_STYLE)
        root.addWidget(self._lbl_program)

        self._lbl_preview = QLabel("Preview: —")
        self._lbl_preview.setStyleSheet(_STATUS_LABEL_STYLE)
        root.addWidget(self._lbl_preview)

        self._lbl_automation = QLabel("Automation: —")
        self._lbl_automation.setStyleSheet(_STATUS_LABEL_STYLE)
        root.addWidget(self._lbl_automation)

        self._lbl_blocked = QLabel("")
        self._lbl_blocked.setStyleSheet(_STATUS_LABEL_STYLE)
        self._lbl_blocked.setVisible(False)
        root.addWidget(self._lbl_blocked)

        # ── Program row (read-only highlight) ─────────────────────────────────
        prog_lbl = QLabel("PROGRAM")
        prog_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(prog_lbl)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(3)
        self._program_buttons: list[tuple[int, QPushButton]] = []
        for input_id, label in self._INPUT_BUTTONS:
            btn = QPushButton(label)
            btn.setStyleSheet(_BTN_BASE)
            btn.setEnabled(False)  # program row is read-only
            prog_row.addWidget(btn)
            self._program_buttons.append((input_id, btn))
        root.addLayout(prog_row)

        # ── Preview row (interactive) ──────────────────────────────────────────
        prev_lbl = QLabel("PREVIEW")
        prev_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(prev_lbl)

        prev_row = QHBoxLayout()
        prev_row.setSpacing(3)
        self._preview_buttons: list[tuple[int, QPushButton]] = []
        for input_id, label in self._INPUT_BUTTONS:
            btn = QPushButton(label)
            btn.setStyleSheet(_BTN_BASE)
            btn.clicked.connect(self._make_preview_handler(input_id))
            btn.installEventFilter(self)
            btn.setProperty("demo_preview_id", input_id)
            prev_row.addWidget(btn)
            self._preview_buttons.append((input_id, btn))
        root.addLayout(prev_row)

        # ── Dry-run display ───────────────────────────────────────────────────
        self._lbl_dry_run = QLabel("Hover a preview button to see dry-run result")
        self._lbl_dry_run.setStyleSheet(_DRY_RUN_STYLE)
        self._lbl_dry_run.setWordWrap(True)
        root.addWidget(self._lbl_dry_run)

        # ── CUT / AUTO ────────────────────────────────────────────────────────
        switch_lbl = QLabel("SWITCH")
        switch_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(switch_lbl)

        switch_row = QHBoxLayout()
        switch_row.setSpacing(6)

        btn_cut = QPushButton("CUT")
        btn_cut.setStyleSheet(_BTN_SWITCH)
        btn_cut.clicked.connect(self._on_cut)
        switch_row.addWidget(btn_cut)

        btn_auto = QPushButton("AUTO")
        btn_auto.setStyleSheet(_BTN_SWITCH)
        btn_auto.clicked.connect(self._on_auto)
        switch_row.addWidget(btn_auto)

        root.addLayout(switch_row)

        # ── Last command result ───────────────────────────────────────────────
        self._lbl_result = QLabel("Last command: —")
        self._lbl_result.setStyleSheet(_RESULT_STYLE)
        self._lbl_result.setWordWrap(True)
        root.addWidget(self._lbl_result)

        # ── Connection controls ───────────────────────────────────────────────
        conn_lbl = QLabel("CONNECTION")
        conn_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(conn_lbl)

        conn_row = QHBoxLayout()
        conn_row.setSpacing(4)

        btn_disconnect = QPushButton("Disconnect")
        btn_disconnect.setStyleSheet(_BTN_CONN)
        btn_disconnect.clicked.connect(self._on_disconnect)
        conn_row.addWidget(btn_disconnect)

        btn_reconnect = QPushButton("Reconnect")
        btn_reconnect.setStyleSheet(_BTN_CONN)
        btn_reconnect.clicked.connect(self._on_reconnect)
        conn_row.addWidget(btn_reconnect)

        root.addLayout(conn_row)

        # ── Automation / safety controls ──────────────────────────────────────
        auto_ctrl_lbl = QLabel("SAFETY")
        auto_ctrl_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(auto_ctrl_lbl)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(4)

        btn_arm = QPushButton("Arm")
        btn_arm.setStyleSheet(_BTN_CONTROL)
        btn_arm.clicked.connect(lambda: (self._dispatcher.set_armed(True), self.refresh()))
        ctrl_row.addWidget(btn_arm)

        btn_disarm = QPushButton("Disarm")
        btn_disarm.setStyleSheet(_BTN_CONTROL)
        btn_disarm.clicked.connect(lambda: (self._dispatcher.set_armed(False), self.refresh()))
        ctrl_row.addWidget(btn_disarm)

        btn_log_only = QPushButton("Log-only")
        btn_log_only.setStyleSheet(_BTN_CONTROL)
        btn_log_only.clicked.connect(lambda: (self._dispatcher.set_log_only(True), self.refresh()))
        ctrl_row.addWidget(btn_log_only)

        btn_clear_guard = QPushButton("Clear Guard")
        btn_clear_guard.setStyleSheet(_BTN_CONTROL)
        btn_clear_guard.clicked.connect(lambda: (self._dispatcher.clear_reconnect_guard(), self.refresh()))
        ctrl_row.addWidget(btn_clear_guard)

        root.addLayout(ctrl_row)

        # ── PiP control ───────────────────────────────────────────────────────
        pip_lbl = QLabel("PIP")
        pip_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(pip_lbl)

        pip_row = QHBoxLayout()
        pip_row.setSpacing(6)

        btn_pip_on = QPushButton("PiP ON")
        btn_pip_on.setStyleSheet(_BTN_SWITCH)
        btn_pip_on.clicked.connect(self._on_pip_on)
        btn_pip_on.setProperty("demo_pip_dry_run", True)
        btn_pip_on.installEventFilter(self)
        pip_row.addWidget(btn_pip_on)

        btn_pip_off = QPushButton("PiP OFF")
        btn_pip_off.setStyleSheet(_BTN_CONTROL)
        btn_pip_off.clicked.connect(self._on_pip_off)
        btn_pip_off.setProperty("demo_pip_dry_run", False)
        btn_pip_off.installEventFilter(self)
        pip_row.addWidget(btn_pip_off)

        self._lbl_pip_state = QLabel("PiP: ○  inactivo")
        self._lbl_pip_state.setStyleSheet(_STATUS_LABEL_STYLE)
        pip_row.addWidget(self._lbl_pip_state)

        root.addLayout(pip_row)

        # ── PiP automation toggle ─────────────────────────────────────────────
        pip_auto_lbl = QLabel("PIP AUTOMATION")
        pip_auto_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(pip_auto_lbl)

        pip_auto_row = QHBoxLayout()
        pip_auto_row.setSpacing(6)

        self._btn_pip_auto_on = QPushButton("Enable PiP Auto")
        self._btn_pip_auto_on.setStyleSheet(_BTN_CONTROL)
        self._btn_pip_auto_on.clicked.connect(lambda: self._set_pip_automation(True))
        pip_auto_row.addWidget(self._btn_pip_auto_on)

        self._btn_pip_auto_off = QPushButton("Disable PiP Auto")
        self._btn_pip_auto_off.setStyleSheet(_BTN_CONTROL)
        self._btn_pip_auto_off.clicked.connect(lambda: self._set_pip_automation(False))
        pip_auto_row.addWidget(self._btn_pip_auto_off)

        self._lbl_pip_auto_status = QLabel("PiP Auto: ON")
        self._lbl_pip_auto_status.setStyleSheet(_STATUS_LABEL_STYLE)
        pip_auto_row.addWidget(self._lbl_pip_auto_status)

        root.addLayout(pip_auto_row)

        # ── PiP nudge settings ────────────────────────────────────────────────
        nudge_lbl = QLabel("PIP NUDGE (cámara platform)")
        nudge_lbl.setStyleSheet(_SECTION_LABEL_STYLE)
        root.addWidget(nudge_lbl)

        nudge_row1 = QHBoxLayout()
        nudge_row1.setSpacing(6)

        lbl_dir = QLabel("Dirección:")
        lbl_dir.setStyleSheet(_STATUS_LABEL_STYLE)
        nudge_row1.addWidget(lbl_dir)

        self._nudge_dir = QComboBox()
        self._nudge_dir.addItems(["right", "left"])
        if self._pip_nudge_svc is not None:
            idx = 1 if self._pip_nudge_svc._cfg.direction == "left" else 0
            self._nudge_dir.setCurrentIndex(idx)
        nudge_row1.addWidget(self._nudge_dir)

        lbl_spd = QLabel("Velocidad (0–24):")
        lbl_spd.setStyleSheet(_STATUS_LABEL_STYLE)
        nudge_row1.addWidget(lbl_spd)

        self._nudge_speed = QSpinBox()
        self._nudge_speed.setRange(0, 24)
        self._nudge_speed.setValue(
            self._pip_nudge_svc._cfg.pan_speed if self._pip_nudge_svc else 0
        )
        nudge_row1.addWidget(self._nudge_speed)

        root.addLayout(nudge_row1)

        nudge_row2 = QHBoxLayout()
        nudge_row2.setSpacing(6)

        lbl_dur = QLabel("Duración ms (0–5000):")
        lbl_dur.setStyleSheet(_STATUS_LABEL_STYLE)
        nudge_row2.addWidget(lbl_dur)

        self._nudge_duration = QSpinBox()
        self._nudge_duration.setRange(0, 5000)
        self._nudge_duration.setSingleStep(50)
        self._nudge_duration.setValue(
            self._pip_nudge_svc._cfg.duration_ms if self._pip_nudge_svc else 0
        )
        nudge_row2.addWidget(self._nudge_duration)

        self._lbl_nudge_status = QLabel(
            self._pip_nudge_svc.describe() if self._pip_nudge_svc else "sin servicio"
        )
        self._lbl_nudge_status.setStyleSheet(_STATUS_LABEL_STYLE)
        nudge_row2.addWidget(self._lbl_nudge_status)

        root.addLayout(nudge_row2)

        # Actualización en vivo al cambiar cualquier control
        self._nudge_speed.valueChanged.connect(self._on_nudge_settings_changed)
        self._nudge_duration.valueChanged.connect(self._on_nudge_settings_changed)
        self._nudge_dir.currentTextChanged.connect(self._on_nudge_settings_changed)

        if self._pip_save_fn is not None:
            btn_save_nudge = QPushButton("Guardar en config.yaml")
            btn_save_nudge.setStyleSheet(_BTN_CONTROL)
            btn_save_nudge.clicked.connect(self._on_save_nudge)
            root.addWidget(btn_save_nudge)

        root.addStretch()

        # ── Polling timer ─────────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(self._REFRESH_INTERVAL_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

        self.refresh()

    # ── Event filter: hover on preview buttons for dry-run ────────────────────

    def eventFilter(self, obj, event):
        if obj is None:
            return super().eventFilter(obj, event)

        # Preview button hover → program dry-run
        preview_id = obj.property("demo_preview_id")
        if preview_id is not None:
            if event.type() == QEvent.Enter:
                result = self._dispatcher.dry_run(preview_id)
                self._lbl_dry_run.setText(f"Dry-run preview {preview_id}: {result}")
            elif event.type() == QEvent.Leave:
                self._lbl_dry_run.setText("Hover a preview button to see dry-run result")
            return super().eventFilter(obj, event)

        # PiP button hover → PiP dry-run
        pip_flag = obj.property("demo_pip_dry_run")
        if pip_flag is not None:
            if event.type() == QEvent.Enter:
                result = self._dispatcher.dry_run_pip(bool(pip_flag))
                self._lbl_dry_run.setText(f"Dry-run PiP {'ON' if pip_flag else 'OFF'}: {result}")
            elif event.type() == QEvent.Leave:
                self._lbl_dry_run.setText("Hover a preview button to see dry-run result")

        return super().eventFilter(obj, event)

    # ── Button handlers ───────────────────────────────────────────────────────

    def _make_preview_handler(self, input_id: int):
        def _handler():
            logger.info("[DEMO PANEL] set_preview_input -> %d", input_id)
            result = self._fake_atem.set_preview_input(input_id)
            self._show_result(result)
            self.refresh()
        return _handler

    def _on_cut(self) -> None:
        logger.info("[DEMO PANEL] CUT")
        result = self._fake_atem.cut()
        self._show_result(result)
        self.refresh()

    def _on_auto(self) -> None:
        logger.info("[DEMO PANEL] AUTO")
        result = self._fake_atem.auto()
        self._show_result(result)
        self.refresh()

    def _on_disconnect(self) -> None:
        logger.info("[DEMO PANEL] disconnect")
        self._fake_atem.disconnect()
        self.refresh()
        self._refresh_main_atem_button()

    def _on_reconnect(self) -> None:
        logger.info("[DEMO PANEL] reconnect")
        self._fake_atem.connect()
        self.refresh()
        self._refresh_main_atem_button()

    def _refresh_main_atem_button(self) -> None:
        """Reflect the FakeATEM connection state on the main-window ATEM dot.

        In demo/sim there is no ATEMMonitor polling, so nothing else
        re-evaluates the button after a manual Disconnect/Reconnect here.
        """
        mw = self.parent()
        if hasattr(mw, '_update_atem_button'):
            mw._update_atem_button(mw._atem_state)

    def set_pip_state(self, active: bool) -> None:
        """Actualiza el indicador de estado PiP (llamado desde MainWindow)."""
        if active:
            self._lbl_pip_state.setText("PiP: ●  ACTIVO")
            self._lbl_pip_state.setStyleSheet(
                "QLabel { color: #E65100; font: bold 10px 'Segoe UI', sans-serif; }"
            )
        else:
            self._lbl_pip_state.setText("PiP: ○  inactivo")
            self._lbl_pip_state.setStyleSheet(_STATUS_LABEL_STYLE)

    def _on_pip_on(self) -> None:
        logger.info("[DEMO PANEL] PiP ON")
        self._dispatcher.on_pip_changed(ATEMPiPState(enabled=True, source=None))
        if self._pip_nudge_svc is not None:
            self._pip_nudge_svc.on_pip_on()
        self.set_pip_state(True)

    def _on_pip_off(self) -> None:
        logger.info("[DEMO PANEL] PiP OFF")
        self._dispatcher.on_pip_changed(ATEMPiPState(enabled=False, source=None))
        if self._pip_nudge_svc is not None:
            self._pip_nudge_svc.on_pip_off()
        self.set_pip_state(False)

    def _on_save_nudge(self) -> None:
        if self._pip_save_fn is None:
            return
        self._pip_save_fn(
            self._nudge_speed.value(),
            self._nudge_dir.currentText(),
            self._nudge_duration.value(),
        )

    def _on_nudge_settings_changed(self) -> None:
        """Aplica los valores de los controles al servicio en vivo."""
        if self._pip_nudge_svc is None:
            return
        self._pip_nudge_svc.update(
            pan_speed=self._nudge_speed.value(),
            direction=self._nudge_dir.currentText(),
            duration_ms=self._nudge_duration.value(),
        )
        self._lbl_nudge_status.setText(self._pip_nudge_svc.describe())

    def _set_pip_automation(self, enabled: bool) -> None:
        self._dispatcher.set_pip_automation_enabled(enabled)
        self._refresh_pip_auto_status()

    def _refresh_pip_auto_status(self) -> None:
        enabled = self._dispatcher.pip_automation_enabled
        self._lbl_pip_auto_status.setText("PiP Auto: ON" if enabled else "PiP Auto: OFF")
        self._btn_pip_auto_on.setEnabled(not enabled)
        self._btn_pip_auto_off.setEnabled(enabled)

    def _show_result(self, result) -> None:
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        if result.ok:
            text = f"[{ts}] OK  {result.command}"
            if result.target is not None:
                text += f" → input {result.target}"
            text += f"  [{result.duration_ms:.1f}ms]"
        else:
            text = f"[{ts}] ERR {result.command}: {result.error_code} — {result.message}"
        self._lbl_result.setText(text)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        status = self._fake_atem.get_status()

        state_text = "Connected" if status.connected else "Disconnected"
        if status.transitioning:
            state_text += " (transitioning)"
        self._lbl_state.setText(f"State: {state_text}")

        self._lbl_program.setText(
            f"Program: {_format_input_label(status.program_input)}"
        )
        self._lbl_preview.setText(
            f"Preview: {_format_input_label(status.preview_input)}"
        )

        auto_text = _format_automation_state(
            self._dispatcher.armed,
            self._dispatcher.log_only,
            self._dispatcher.reconnect_guard,
            self._dispatcher.pip_automation_enabled,
        )
        self._lbl_automation.setText(f"Automation: {auto_text}")

        blocked = self._dispatcher.get_blocked_reason()
        if blocked:
            self._lbl_blocked.setText(f"Blocked: {blocked}")
            self._lbl_blocked.setVisible(True)
        else:
            self._lbl_blocked.setVisible(False)

        self._refresh_pip_auto_status()

        # Program buttons (read-only highlight)
        for input_id, btn in self._program_buttons:
            btn.setStyleSheet(
                _BTN_SELECTED if input_id == status.program_input else _BTN_BASE
            )

        # Preview buttons (interactive highlight)
        for input_id, btn in self._preview_buttons:
            btn.setStyleSheet(
                _BTN_PREVIEW_SELECTED if input_id == status.preview_input else _BTN_BASE
            )
