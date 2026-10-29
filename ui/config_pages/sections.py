# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/sections.py — ConfigDialog section builders (#894)
#
# These functions were methods on ConfigDialog. They are pure builders: given the
# dialog instance and a target layout, they populate it. They use the dialog's
# shared helpers via the `dialog` argument (dialog._btn, dialog._toast,
# dialog._status_pill). No `self` — the only object state they touch is the
# ConfigDialog passed in. Behaviour is identical to the former methods.

from __future__ import annotations

from PyQt5.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import adapters.sim_mode as _sim_mode
from ui.styles import (
    BRAND_DARK as _C_BRAND_DARK,
    CARD_BD as _C_CARD_BD,
    ERROR as _C_ERROR,
    FIELD_BD as _C_FIELD_BD,
    MUTED as _C_MUTED,
    SECONDARY as _C_SECONDARY,
    svg_icon_from_markup as _svg_icon_markup,
    WARNING as _C_WARNING,
    WARNING_BD as _C_WARNING_BD,
    WARNING_BG as _C_WARNING_BG,
)


def build_second_platform_section(dialog, layout, mw):
    """Toggle para la segunda plataforma (botón 'Platform 2', preset 132).

    Por defecto desactivado. Persiste en el directorio de datos de runtime
    (display_prefs.json) — funciona en producción, demo y simulación. El
    botón se muestra/oculta en vivo, sin reiniciar.
    """
    from application.display_prefs import (
        is_second_platform_enabled,
        set_second_platform_enabled,
    )

    enabled = is_second_platform_enabled()

    if enabled:
        pill = dialog._status_pill('Second platform ON', state='ok',
                                   meta='Platform 2 button (preset 132)')
    else:
        pill = dialog._status_pill('Second platform OFF', state='neutral',
                                   meta='hidden by default')
    layout.addWidget(pill)

    info = QLabel(
        "Adds a small Platform 2 button to the top-right of the platform.\n"
        "It recalls preset 132 on the platform camera and can store a position (SET)."
    )
    info.setStyleSheet(f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};")
    info.setWordWrap(True)
    layout.addWidget(info)

    btn_toggle = dialog._btn(
        'Disable Second Platform' if enabled else 'Enable Second Platform',
        variant='danger' if enabled else 'primary',
        icon='minus' if enabled else 'plus',
    )

    def _toggle_second_platform():
        new_value = not is_second_platform_enabled()
        # Persist first, but do NOT abort if it fails: on a production Pi the
        # runtime data dir can be non-writable by the service user, and the
        # old code reacted by showing a blocking error and doing nothing —
        # so the operator could never enable Platform 2. Apply the change for
        # this session regardless; only warn that it won't survive a restart.
        persisted = set_second_platform_enabled(new_value)

        # Aplicar en vivo en la ventana principal.
        try:
            mw.apply_second_platform_visibility(new_value)
        except Exception:  # noqa: BLE001
            pass
        btn_toggle.setText(
            'Disable Second Platform' if new_value else 'Enable Second Platform'
        )

        if persisted:
            dialog._toast(
                'Second platform enabled' if new_value else 'Second platform disabled'
            )
        else:
            dialog._toast(
                'Applied for this session — could not save (read-only data dir)'
            )

    btn_toggle.clicked.connect(_toggle_second_platform)
    layout.addWidget(btn_toggle, 0, Qt.AlignRight)


def build_sim_section(dialog, layout, mw, sim_active: bool):
    """Sección de modo simulación: toggle ON/OFF + Advanced accordion."""
    if sim_active:
        pill = dialog._status_pill('Cameras simulated locally', state='ok',
                                   meta='no VISCA-IP traffic')
    else:
        pill = dialog._status_pill('Using real hardware', state='neutral',
                                   meta='VISCA-IP active')
    layout.addWidget(pill)

    if sim_active:
        btn_toggle = dialog._btn('Disable Simulation Mode', variant='danger', icon='minus')
    else:
        btn_toggle = dialog._btn('Enable Simulation Mode', variant='primary', icon='play')

    def _toggle_sim():
        # Switching to real hardware mid-air is significant — confirm it.
        if _sim_mode.is_active() and not dialog._confirm_danger(
            'Disable Simulation Mode',
            'Switch to real camera hardware?\n'
            'The app will talk to the live VISCA-IP cameras after restart.',
            'Disable Simulation',
        ):
            return
        try:
            if _sim_mode.is_active():
                _sim_mode.deactivate()
            else:
                _sim_mode.activate()
        except RuntimeError as exc:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(None, "Simulation Mode",
                                str(exc) or "Unknown error toggling simulation mode.")
            return
        dialog._toast('Simulation mode changed — restart to apply',
                      kind='warn', duration=4200)

    btn_toggle.clicked.connect(_toggle_sim)
    layout.addWidget(btn_toggle, 0, Qt.AlignRight)

    # ── Advanced accordion: collapsed by default ───────────────────────
    runtime_mode = dialog._current_runtime_mode(sim_active)

    adv_toggle = QPushButton('▸  Advanced — restart & runtime profile')
    adv_toggle.setCheckable(True)
    adv_toggle.setChecked(False)
    adv_toggle.setStyleSheet(
        "QPushButton {"
        "  background: transparent; border: none;"
        f"  border-top: 1px dashed {_C_CARD_BD}; margin-top: 2px;"
        "  padding: 10px 2px 2px; text-align: left;"
        "  font: 600 11.5px 'Inter Tight', 'Segoe UI'; color: #666666;"
        "}"
        f"QPushButton:hover {{ color: {_C_BRAND_DARK}; }}"
        "QPushButton:checked { color: #333333; }"
    )

    adv_widget = QWidget()
    adv_widget.setStyleSheet("background: transparent;")
    adv_layout = QVBoxLayout(adv_widget)
    adv_layout.setContentsMargins(0, 4, 0, 0)
    adv_layout.setSpacing(8)

    adv_layout.addWidget(dialog._info_line('Current runtime profile', runtime_mode.upper()))

    _live = getattr(mw, 'session_active', False)
    restart_row = QHBoxLayout()
    restart_row.setSpacing(8)
    for mode in ("production", "demo"):
        if mode == runtime_mode:
            continue
        btn_mode = dialog._btn(f'Restart · {mode.title()}', variant='ghost', width='row', icon='refresh')
        btn_mode.clicked.connect(
            lambda _=False, target=mode: dialog._restart_in_runtime_mode(mw, target)
        )
        dialog._lock_if_live(btn_mode, _live,
                             'Stop the session before restarting the app')
        restart_row.addWidget(btn_mode)
    adv_layout.addLayout(restart_row)

    adv_widget.setVisible(False)

    def _toggle_adv(checked: bool) -> None:
        adv_widget.setVisible(checked)
        adv_toggle.setText(
            '▾  Advanced — restart & runtime profile' if checked
            else '▸  Advanced — restart & runtime profile'
        )

    adv_toggle.toggled.connect(_toggle_adv)
    layout.addWidget(adv_toggle)
    layout.addWidget(adv_widget)


def build_preset_validation_section(dialog, layout, mw):
    """Preset Validation panel for Settings → 🛠 Test.

    Runs all configured seat presets sequentially, shows progress and a
    final summary. Runner logic lives in application/preset_test_runner.py
    so the layout editor can reuse it later without touching this file.
    """
    from PyQt5.QtWidgets import QMessageBox, QTextEdit

    from application.preset_sources import build_items_from_config, build_items_from_assigned_names
    from application.preset_test_runner import PresetTestRunner
    from application.preset_test_models import STATUS_WARNING, STATUS_ERROR, STATUS_SKIPPED

    # ── Intro text ────────────────────────────────────────────────────
    intro = QLabel(
        "Calls each configured seat preset in order.\n"
        "Do not run during a live session."
    )
    intro.setStyleSheet(
        f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
    )
    intro.setWordWrap(True)
    layout.addWidget(intro)

    # ── Last run label ────────────────────────────────────────────────
    try:
        from application.preset_test_history_service import PresetTestHistoryService
        _last_run_text = PresetTestHistoryService().summary_line()
    except Exception:
        _last_run_text = ""
    lbl_last_run = QLabel(_last_run_text)
    lbl_last_run.setStyleSheet("QLabel { color: #666666; font-size: 12px; }")
    lbl_last_run.setAlignment(Qt.AlignLeft)
    layout.addWidget(lbl_last_run)

    # ── Buttons ───────────────────────────────────────────────────────
    btn_row = QHBoxLayout()
    btn_run = dialog._btn('Test All Presets', variant='primary', width='row', icon='play')
    btn_run_named = dialog._btn('Named Seats Only', variant='ghost', width='row', icon='play')
    btn_cancel = dialog._btn('Cancel', variant='ghost', width='row', icon='square')
    btn_cancel.setEnabled(False)
    btn_row.addWidget(btn_run)
    btn_row.addWidget(btn_run_named)
    btn_row.addWidget(btn_cancel)
    layout.addLayout(btn_row)

    # Preset tests physically move the cameras — never during a live session.
    _live = getattr(mw, 'session_active', False)
    dialog._lock_if_live(btn_run, _live,
                       'Stop the session before testing presets')
    dialog._lock_if_live(btn_run_named, _live,
                       'Stop the session before testing presets')

    # ── Current item + progress ───────────────────────────────────────
    lbl_current = QLabel('—')
    lbl_current.setStyleSheet(
        f"font: 600 12px 'Inter Tight', 'Segoe UI'; color: {_C_SECONDARY};"
    )
    lbl_progress = QLabel('')
    lbl_progress.setStyleSheet(
        f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
    )
    layout.addWidget(lbl_current)
    layout.addWidget(lbl_progress)

    # ── Summary area ─────────────────────────────────────────────────
    txt_summary = QTextEdit()
    txt_summary.setReadOnly(True)
    txt_summary.setFixedHeight(100)
    txt_summary.setStyleSheet(
        f"font: 11px 'Consolas', 'Courier New', monospace; color: {_C_SECONDARY};"
        f" background: #F8F9F6; border: 1px solid {_C_FIELD_BD}; border-radius: 8px;"
    )
    txt_summary.setVisible(False)
    layout.addWidget(txt_summary)

    # ── Qt signal bridge (runner runs in a worker thread) ─────────────
    class _Signals(QObject):
        started      = pyqtSignal(int)
        item_started = pyqtSignal(object, int, int)
        item_result  = pyqtSignal(object)
        finished     = pyqtSignal(object)
        cancelled    = pyqtSignal(object)
        highlight    = pyqtSignal(object, str)

    _sig = _Signals()
    _runner_ref: list = [None]  # mutable cell for closure

    # ── Callbacks wired to signals ────────────────────────────────────
    def _on_started(total):
        _sig.started.emit(total)

    def _on_item_started(item, idx, total):
        _sig.item_started.emit(item, idx, total)

    def _on_item_result(result):
        _sig.item_result.emit(result)

    def _on_finished(summary):
        _sig.finished.emit(summary)
        try:
            from application.preset_test_history_service import PresetTestHistoryService
            PresetTestHistoryService().record(
                total=summary.total,
                ok=summary.ok,
                warning=summary.warning,
                error=summary.error,
                skipped=summary.skipped,
                cancelled=summary.cancelled,
            )
        except Exception:
            pass

    def _on_cancelled(summary):
        _sig.cancelled.emit(summary)

    def _on_highlight(item, state):
        _sig.highlight.emit(item, state)

    # ── Signal handlers (Qt main thread) ─────────────────────────────
    def _handle_started(total):
        btn_run.setEnabled(False)
        btn_run_named.setEnabled(False)
        btn_cancel.setEnabled(True)
        lbl_current.setText('Starting…')
        lbl_progress.setText(f'0 / {total}')
        txt_summary.setVisible(False)
        txt_summary.clear()

    def _handle_item_started(item, idx, total):
        cam = item.camera_role
        name_part = f'  ·  {item.assigned_name}' if item.assigned_name else ''
        lbl_current.setText(f'Seat {item.label}{name_part}  ·  {cam}')
        lbl_progress.setText(f'{idx + 1} / {total}')

    def _handle_item_result(_result):
        pass

    def _reset_ui():
        btn_run.setEnabled(True)
        btn_run_named.setEnabled(True)
        btn_cancel.setEnabled(False)

    def _seat_label(item) -> str:
        if item.assigned_name:
            return f'Seat {item.label} / {item.assigned_name}'
        return f'Seat {item.label}'

    def _format_summary(summary, cancelled: bool) -> str:
        head = 'Test cancelled — partial results:' if cancelled else 'Preset test complete'
        lines = [
            head,
            f'  OK: {summary.ok}   WARNING: {summary.warning}'
            f'   ERROR: {summary.error}   SKIPPED: {summary.skipped}',
        ]
        warnings = [r for r in summary.results if r.status == STATUS_WARNING]
        errors = [r for r in summary.results if r.status == STATUS_ERROR]
        skipped = [r for r in summary.results if r.status == STATUS_SKIPPED]
        if warnings:
            lines.append('')
            lines.append('Missing PTZ metadata (callable but unverified):')
            for r in warnings:
                lines.append(f'  {_seat_label(r.item)}: {r.item.camera_role}')
        if errors:
            lines.append('')
            lines.append('Errors:')
            for r in errors:
                dur = f'  ({r.duration_ms} ms)' if r.duration_ms else ''
                lines.append(f'  {_seat_label(r.item)}: {r.message}{dur}')
        if skipped:
            lines.append('')
            lines.append('Skipped:')
            for r in skipped:
                lines.append(f'  {_seat_label(r.item)}: {r.message}')
        return '\n'.join(lines)

    def _handle_finished(summary):
        _reset_ui()
        lbl_current.setText('Done')
        lbl_progress.setText(
            f'OK {summary.ok} · WARNING {summary.warning}'
            f' · ERROR {summary.error} · SKIPPED {summary.skipped}'
        )
        txt_summary.setPlainText(_format_summary(summary, cancelled=False))
        txt_summary.setVisible(True)
        try:
            from application.preset_test_history_service import PresetTestHistoryService
            lbl_last_run.setText(PresetTestHistoryService().summary_line())
        except Exception:
            pass

    def _handle_cancelled(summary):
        _reset_ui()
        lbl_current.setText('Cancelled')
        lbl_progress.setText(
            f'OK {summary.ok} · WARNING {summary.warning}'
            f' · ERROR {summary.error} · SKIPPED {summary.skipped}'
        )
        txt_summary.setPlainText(_format_summary(summary, cancelled=True))
        txt_summary.setVisible(True)

    def _handle_highlight(item, state):
        if item.preset is None:
            return
        btn = getattr(mw, f"Seat{item.preset}", None)
        if btn is not None and hasattr(btn, 'show_test_result'):
            btn.show_test_result(state)

    _sig.started.connect(_handle_started)
    _sig.item_started.connect(_handle_item_started)
    _sig.item_result.connect(_handle_item_result)
    _sig.finished.connect(_handle_finished)
    _sig.cancelled.connect(_handle_cancelled)
    _sig.highlight.connect(_handle_highlight)

    # ── Resolve + send helpers ────────────────────────────────────────
    def _resolve(preset_number: int):
        from config import CAM1 as _C1, CAM2 as _C2
        if preset_number <= 3:
            return _C1.ip, _C1.cam_id
        return _C2.ip, _C2.cam_id

    def _send(ip: str, cam_id: str, preset_hex: str) -> bool:
        from config import CAM1 as _C1
        cam = 1 if ip == _C1.ip else 2
        slot = int(preset_hex, 16)
        return mw._camera_svc.recall_preset(cam, slot)

    # ── Button actions ────────────────────────────────────────────────
    def _start_run(items):
        runner = PresetTestRunner(items, _send, _resolve)
        runner.on_started      = _on_started
        runner.on_item_started = _on_item_started
        runner.on_item_result  = _on_item_result
        runner.on_finished     = _on_finished
        runner.on_cancelled    = _on_cancelled
        runner.on_highlight    = _on_highlight
        _runner_ref[0] = runner
        btn_run.setEnabled(False)
        btn_run_named.setEnabled(False)
        btn_cancel.setEnabled(True)
        runner.start()

    def _on_run():
        items = build_items_from_config()
        if not items:
            QMessageBox.warning(
                dialog, 'Preset Validation', 'No configured presets found.'
            )
            return
        reply = QMessageBox.question(
            dialog,
            'Preset Validation',
            'This will move cameras through all configured seat presets.\n'
            'Do not run during a live event.\n\nContinue?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        _start_run(items)

    def _on_run_named():
        items = build_items_from_assigned_names()
        if not items:
            QMessageBox.information(
                dialog, 'Preset Validation',
                'No named seats found.\n'
                'Assign names to seats first or use Test All Presets.'
            )
            return
        reply = QMessageBox.question(
            dialog,
            'Preset Validation',
            f'This will move cameras through {len(items)} named seat preset(s).\n'
            'Do not run during a live event.\n\nContinue?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        _start_run(items)

    def _stop_runner():
        runner = _runner_ref[0]
        if runner and runner.is_running:
            runner.cancel()

    def _on_cancel():
        _stop_runner()
        btn_cancel.setEnabled(False)

    btn_run.clicked.connect(_on_run)
    btn_run_named.clicked.connect(_on_run_named)
    btn_cancel.clicked.connect(_on_cancel)

    # Only stop the runner on close — never touch widgets from destroyed signal.
    dialog.destroyed.connect(lambda _=None: _stop_runner())


def build_atem_automation_section(dialog, layout, mw):
    # ConfigDialog-local button width and icon set (lazy import avoids a cycle).
    from ui.config_dialog import _BTN_STD, _ICON_SVGS
    """Controles de automatización ATEM: armado/desarmado, dry-run, reconnect guard."""
    from PyQt5.QtWidgets import QMessageBox, QInputDialog

    dispatcher = getattr(mw, '_atem_dispatcher', None)
    if dispatcher is None:
        layout.addWidget(QLabel('Dispatcher no disponible.'))
        return

    # No switcher configured → nothing to automate. Show a hint and disable
    # the arm control so automation can't be enabled against a missing ATEM.
    from config import ATEM as _atem_cfg, is_valid_ip as _is_valid_ip_auto
    atem_configured = _is_valid_ip_auto(_atem_cfg.ip)
    if not atem_configured:
        _no_atem_lbl = QLabel(
            'No ATEM configured — set the ATEM IP (ATEM Switcher) to enable '
            'automation.'
        )
        _no_atem_lbl.setStyleSheet(
            f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_WARNING};"
            f" background: {_C_WARNING_BG}; border: 1px solid {_C_WARNING_BD};"
            " border-radius: 8px; padding: 7px 10px;"
        )
        _no_atem_lbl.setWordWrap(True)
        layout.addWidget(_no_atem_lbl)

    # ── Estado armado ─────────────────────────────────────────────────────
    _arm_pill_state = [None]

    def _make_arm_pill():
        if dispatcher.armed:
            return dialog._status_pill('Armed — live', state='ok',
                                     meta='PTZ output')
        return dialog._status_pill('Disarmed', state='neutral',
                                 meta='monitor only')

    arm_pill_container = QVBoxLayout()
    arm_pill_container.setContentsMargins(0, 0, 0, 0)
    _arm_pill_state[0] = _make_arm_pill()
    arm_pill_container.addWidget(_arm_pill_state[0])
    layout.addLayout(arm_pill_container)

    def _refresh_arm_lbl():
        old = _arm_pill_state[0]
        new_pill = _make_arm_pill()
        arm_pill_container.replaceWidget(old, new_pill)
        old.deleteLater()
        _arm_pill_state[0] = new_pill

    # ── Botón armar / desarmar ────────────────────────────────────────────
    btn_arm = QPushButton()
    btn_arm.setMinimumHeight(36)
    btn_arm.setFixedWidth(_BTN_STD)
    btn_arm.setCursor(Qt.PointingHandCursor)
    btn_arm.setIcon(_svg_icon_markup(_ICON_SVGS['bolt'], 14, color='white'))
    btn_arm.setIconSize(QSize(14, 14))

    def _update_arm_btn():
        if dispatcher.armed:
            btn_arm.setText('Disarm Automation')
            btn_arm.setStyleSheet(
                f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f" stop:0 {_C_ERROR}, stop:1 #8E0F18);"
                " border: none; border-radius: 9px;"
                " font: 600 12.5px 'Inter Tight', 'Segoe UI'; color: white; padding: 5px 14px; }"
                "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #d41828, stop:1 #a01020); }"
                "QPushButton:pressed { background: #6E080F; }"
            )
        else:
            btn_arm.setText('Arm ATEM Automation')
            btn_arm.setStyleSheet(
                "QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                " stop:0 #1976D2, stop:1 #0D5FA3);"
                " border: none; border-radius: 9px;"
                " font: 600 12.5px 'Inter Tight', 'Segoe UI'; color: white; padding: 5px 14px; }"
                "QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #2080dc, stop:1 #1468b0); }"
                "QPushButton:pressed { background: #0A4A80; }"
            )

    _update_arm_btn()

    if not atem_configured:
        btn_arm.setEnabled(False)
        btn_arm.setToolTip('Configure the ATEM IP first (ATEM Switcher)')

    def _refresh_all():
        _refresh_arm_lbl()
        _update_arm_btn()
        if not atem_configured:
            btn_arm.setEnabled(False)
        _refresh_guard()

    def _on_arm_toggle():
        if dispatcher.armed:
            dispatcher.set_armed(False)
            _refresh_all()
        else:
            reply = QMessageBox.question(
                dialog, 'Arm ATEM Automation',
                'Enable live ATEM automation?\n\n'
                'Camera actions will be triggered automatically when\n'
                'the ATEM program input changes.',
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if reply != QMessageBox.Ok:
                return
            text, ok = QInputDialog.getText(
                dialog, 'Confirm', 'Type  ENABLE ATEM  to activate live automation:'
            )
            if ok and text.strip() == 'ENABLE ATEM':
                dispatcher.set_armed(True)
                dispatcher.clear_reconnect_guard()
                _refresh_all()

    btn_arm.clicked.connect(_on_arm_toggle)
    layout.addWidget(btn_arm, 0, Qt.AlignRight)

    # ── Reconnect guard ───────────────────────────────────────────────────
    guard_lbl = QLabel()
    guard_lbl.setAlignment(Qt.AlignCenter)
    guard_lbl.setWordWrap(True)

    btn_guard = dialog._btn('Clear Reconnect Guard', variant='ghost')

    def _refresh_guard():
        if dispatcher.reconnect_guard:
            guard_lbl.setText(
                'Reconnect guard active — automation paused after reconnect.'
            )
            guard_lbl.setStyleSheet(
                f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_WARNING};"
                f" background: {_C_WARNING_BG}; border: 1px solid {_C_WARNING_BD};"
                " border-radius: 8px; padding: 7px 10px;"
            )
            guard_lbl.show()
            btn_guard.show()
        else:
            guard_lbl.hide()
            btn_guard.hide()

    _refresh_guard()

    def _on_clear_guard():
        dispatcher.clear_reconnect_guard()
        _refresh_guard()

    btn_guard.clicked.connect(_on_clear_guard)
    layout.addWidget(guard_lbl)
    layout.addWidget(btn_guard, 0, Qt.AlignRight)

    # Actualizar guard si el ATEM reconecta mientras el diálogo está abierto
    def _on_atem_state_for_guard(_state):
        _refresh_guard()

    mw.atem_state_changed.connect(_on_atem_state_for_guard)
    def _on_guard_destroyed(_=None) -> None:
        try:
            dialog._disconnect_signal(mw.atem_state_changed, _on_atem_state_for_guard)
        except RuntimeError:
            pass  # mw already deleted during app shutdown

    dialog.destroyed.connect(_on_guard_destroyed)

# ── Usability helpers ─────────────────────────────────────────────────────


def build_status_strip(dialog, mw):
    from config import CAM1, CAM2  # read-only status display
    """Global status strip (design section B): cam1 · cam2 · ATEM · Auto · profile.

    CAM1/CAM2.check is the string "Green" or "Red" (set by check_all_cameras()).
    """
    from domain.atem_state import ATEMState as _ATEMState

    # LED indicators share the glossy round look from _set_led(); the strip
    # just resolves each item to a state key ('green'/'red'/'amber'/'off').
    def _cam_state(cam_obj) -> str:
        """Return LED state from the "Green"/"Red" check string."""
        return 'green' if getattr(cam_obj, 'check', 'Red') == 'Green' else 'red'

    def _cam_label(cam_obj, role: str) -> str:
        return role if getattr(cam_obj, 'check', 'Red') == 'Green' else 'Offline'

    def _atem_state_led(state) -> str:
        if state == _ATEMState.CONNECTED:
            return 'green'
        if state in (_ATEMState.CONNECTING, _ATEMState.RECONNECTING):
            return 'amber'
        if state in (_ATEMState.DISCONNECTED, _ATEMState.ERROR):
            return 'red'
        return 'off'

    def _atem_label(state) -> str:
        # Compact tokens — the strip is a glanceable status row that must fit
        # the fixed dialog width; the full wording lives in the ATEM tab.
        return {
            _ATEMState.CONNECTED:          'Linked',
            _ATEMState.CONNECTING:         'Conn…',
            _ATEMState.RECONNECTING:       'Recon…',
            _ATEMState.DISCONNECTED:       'Down',
            _ATEMState.ERROR:              'Error',
            _ATEMState.NOT_CONFIGURED:     'None',
            _ATEMState.DEPENDENCY_MISSING: 'No lib',
        }.get(state, 'Unknown')

    # ── Strip shell ──────────────────────────────────────────────────
    strip = QWidget()
    strip.setObjectName('StatusStrip')
    strip.setStyleSheet(
        "QWidget#StatusStrip {"
        "  background: qlineargradient(x1:0,y1:0,x2:0,y2:1,"
        "    stop:0 #EEF3EC, stop:1 #E6EDE3);"
        f"  border-top: 1px solid {_C_CARD_BD};"
        "  border-bottom: 1px solid #D7DED4;"
        "}"
    )
    h = QHBoxLayout(strip)
    h.setContentsMargins(14, 0, 14, 0)
    h.setSpacing(0)

    def _make_led(state: str) -> QLabel:
        return dialog._led(state)

    def _sep() -> QFrame:
        f = QFrame()
        f.setFixedWidth(1)
        f.setFixedHeight(20)
        f.setStyleSheet("background: #E4E7E2; border: none;")
        return f

    def _strip_item(key: str, value: str, state: str):
        """Returns (container_widget, led_dot, value_label)."""
        item = QWidget()
        item.setStyleSheet("background: transparent;")
        ih = QHBoxLayout(item)
        ih.setContentsMargins(0, 8, 0, 8)
        ih.setSpacing(7)
        dot = _make_led(state)
        ih.addWidget(dot)
        k_lbl = QLabel(key)
        k_lbl.setStyleSheet(
            "font: 700 10px 'Inter Tight', 'Segoe UI', sans-serif;"
            f" color: {_C_MUTED}; letter-spacing: 0.08em; background: transparent;"
        )
        ih.addWidget(k_lbl)
        v_lbl = QLabel(value)
        v_lbl.setStyleSheet(
            "font: 600 11px 'Inter Tight', 'Segoe UI';"
            f" color: {_C_SECONDARY}; background: transparent;"
        )
        ih.addWidget(v_lbl)
        return item, dot, v_lbl

    def _add_sep():
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        wh = QHBoxLayout(wrap)
        wh.setContentsMargins(8, 0, 8, 0)
        wh.setSpacing(0)
        wh.addWidget(_sep())
        h.addWidget(wrap)

    # Cam 1
    item1, dot1, val1 = _strip_item(
        'CAM 1', _cam_label(CAM1, 'Platform'), _cam_state(CAM1)
    )
    h.addWidget(item1)
    _add_sep()

    # Cam 2
    item2, dot2, val2 = _strip_item(
        'CAM 2', _cam_label(CAM2, 'Comments'), _cam_state(CAM2)
    )
    h.addWidget(item2)
    _add_sep()

    # Expose the strip cam indicators so a live re-check (after assigning a
    # discovered IP) can refresh them without reopening the dialog.
    dialog._strip_cam = {1: (dot1, val1, 'Platform'), 2: (dot2, val2, 'Comments')}

    # ATEM
    _mon        = getattr(mw, '_atem_monitor', None)
    _atem_state = getattr(_mon, 'state', None)
    item_atem, dot_atem, val_atem = _strip_item(
        'ATEM', _atem_label(_atem_state), _atem_state_led(_atem_state)
    )
    h.addWidget(item_atem)
    _add_sep()

    # Auto-arm
    _dispatcher = getattr(mw, '_atem_dispatcher', None)
    _armed      = getattr(_dispatcher, 'armed', False) if _dispatcher else False
    item_auto, dot_auto, val_auto = _strip_item(
        'AUTO', 'Armed' if _armed else 'Disarmed',
        'green' if _armed else 'off',
    )
    h.addWidget(item_auto)
    h.addStretch()

    # Runtime profile badge
    runtime_mode = dialog._current_runtime_mode(_sim_mode.is_active())
    profile_lbl = QLabel(runtime_mode.upper())
    profile_lbl.setStyleSheet(
        "font: 700 10px 'Consolas', 'Courier New', monospace;"
        f" letter-spacing: 0.08em; color: {_C_WARNING};"
        f" background: {_C_WARNING_BG}; border: 1px solid {_C_WARNING_BD};"
        " padding: 5px 9px; border-radius: 999px;"
    )
    h.addWidget(profile_lbl)

    # ── Live ATEM update ─────────────────────────────────────────────
    def _on_strip_atem_state(state):
        try:
            dialog._set_led(dot_atem, _atem_state_led(state))
            val_atem.setText(_atem_label(state))
        except RuntimeError:
            pass

    if hasattr(mw, 'atem_state_changed'):
        mw.atem_state_changed.connect(_on_strip_atem_state)

        def _on_strip_destroyed(_=None) -> None:
            try:
                dialog._disconnect_signal(
                    mw.atem_state_changed, _on_strip_atem_state
                )
            except RuntimeError:
                pass

        dialog.destroyed.connect(_on_strip_destroyed)

    return strip

# ── Static design helpers ─────────────────────────────────────────────────
