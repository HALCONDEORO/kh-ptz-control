# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/atem_tab.py — ConfigDialog "ATEM" tab (#894 phase 3)
#
# ATEM switcher config + discovery + status/scan + the automation card.
# Extracted from ConfigDialog._build_ui; self -> dialog; is_on, sim_active and
# _panel_layout are params. ATEM IP writes route through CameraConfigService.

from __future__ import annotations

import socket
import threading

from config import ATEM
from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ui.config_edit_dialogs import _ATEMEditDialog
from ui.config_pages.sections import build_atem_automation_section
from ui.styles import (
    CARD_BD as _C_CARD_BD,
    ERROR as _C_ERROR,
    ERROR_BD as _C_ERROR_BD,
    ERROR_BG as _C_ERROR_BG,
    FIELD_BG as _C_FIELD_BG,
    MUTED as _C_MUTED,
    SECONDARY as _C_SECONDARY,
    SUCCESS as _C_SUCCESS,
    SUCCESS_BD as _C_SUCCESS_BD,
    SUCCESS_BG as _C_SUCCESS_BG,
    WARNING as _C_WARNING,
    WARNING_BD as _C_WARNING_BD,
    WARNING_BG as _C_WARNING_BG,
    primary_button_qss,
)


def build_atem_tab(dialog, atem_layout, mw, is_on, sim_active, panel_layout):
    """Populate the ATEM tab: switcher config, discovery, status and automation."""
    # ── ATEM: Switcher + Automation stacked in one column ──────────────
    # Single column (not the design's 2-up grid): on this taller dialog body
    # two short side-by-side cards left a huge empty band underneath. Stacking
    # fills the space and keeps each card full-width like the other tabs.
    _atem_col1_l = atem_layout
    _atem_col2_l = atem_layout

    # ── Sección: ATEM Switcher ────────────────────────────────────────
    layout = panel_layout(_atem_col1_l, 'ATEM Switcher')

    atem_row_w = dialog._field_row('IP', ATEM.ip, on_edit=None)
    _atem_val_lbl = atem_row_w.findChild(QLabel, 'field_value')
    btn_atem_ip_w = atem_row_w.findChild(QPushButton)
    if btn_atem_ip_w:
        def _edit_atem_ip(_, lbl=_atem_val_lbl):
            _ATEMEditDialog(dialog, mw).exec_()
            import config as _cfg
            if lbl:
                lbl.setText(_cfg.ATEM.ip)
        btn_atem_ip_w.clicked.connect(_edit_atem_ip)
        dialog._lock_if_live(btn_atem_ip_w, is_on,
                           'Stop the session before changing the ATEM IP',
                           dim_target=atem_row_w)
    layout.addWidget(atem_row_w)

    # Field-row bottom separator
    _atem_sep = QFrame()
    _atem_sep.setFrameShape(QFrame.HLine)
    _atem_sep.setFixedHeight(1)
    _atem_sep.setStyleSheet("background: #F0F1EE; border: none;")
    layout.addWidget(_atem_sep)

    # ── ATEM Discovery ────────────────────────────────────────────────────
    # Find a switcher when its IP is unknown. The "Scan" button below only
    # probes the *configured* IP, so without this there was no way to set an
    # ATEM you didn't already know the address of. Scans the camera subnet on
    # the ATEM control port (9910) off the GUI thread.
    atem_disc_desc = QLabel(
        "Don't know the ATEM's IP? Discover switchers on the local network."
    )
    atem_disc_desc.setWordWrap(True)
    atem_disc_desc.setStyleSheet(
        f"font: 400 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
        " background: transparent;"
    )
    layout.addWidget(atem_disc_desc)

    atem_disc_status = QLabel('')
    atem_disc_status.setWordWrap(True)
    atem_disc_status.setStyleSheet(
        f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_SECONDARY};"
        " padding: 2px 0; background: transparent;"
    )
    layout.addWidget(atem_disc_status)

    atem_disc_inner = QWidget()
    atem_disc_inner.setStyleSheet("background: transparent;")
    atem_disc_layout = QVBoxLayout(atem_disc_inner)
    atem_disc_layout.setContentsMargins(0, 0, 0, 0)
    atem_disc_layout.setSpacing(4)

    atem_disc_scroll = QScrollArea()
    atem_disc_scroll.setWidgetResizable(True)
    atem_disc_scroll.setFixedHeight(0)   # hidden until there are results
    atem_disc_scroll.setFrameShape(QFrame.NoFrame)
    atem_disc_scroll.setStyleSheet("background: transparent;")
    atem_disc_scroll.setWidget(atem_disc_inner)
    layout.addWidget(atem_disc_scroll)

    btn_atem_discover = dialog._btn('Discover switchers', variant='primary', icon='search')
    layout.addWidget(btn_atem_discover, 0, Qt.AlignRight)

    def _atem_clear_results():
        while atem_disc_layout.count():
            child = atem_disc_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _atem_use_ip(ip: str):
        """Assign a discovered ATEM IP, persist it and reconnect the monitor."""
        svc = getattr(mw, '_camera_config', None)
        result = svc.set_atem_ip(ip) if svc is not None else None
        persisted = bool(result and result.ok and result.code == "OK")
        if _atem_val_lbl:
            _atem_val_lbl.setText(ip)
        # The configured-IP Scan button is now usable.
        btn_scan_atem.setEnabled(True)
        btn_scan_atem.setToolTip('')
        last_error_lbl.setVisible(False)
        dialog._toast(
            f'ATEM → {ip} assigned and saved' if persisted
            else f'ATEM → {ip} assigned (this session only)',
            kind='ok' if persisted else 'warn',
        )
        mw._do_restart_atem_monitor()
        _set_atem_status(_ATEMState.CONNECTING)

    def _atem_show_results(found: list):
        _atem_clear_results()
        if not found:
            atem_disc_status.setText('No ATEM switchers found on the network.')
            atem_disc_scroll.setFixedHeight(0)
        else:
            atem_disc_status.setText(f'{len(found)} switcher(s) found:')
            for ip in found:
                row_w = QWidget()
                row_w.setStyleSheet(
                    f"background: {_C_FIELD_BG}; border-radius: 8px;"
                    f" border: 1px solid {_C_CARD_BD};"
                )
                row_h = QHBoxLayout(row_w)
                row_h.setContentsMargins(10, 4, 6, 4)
                row_h.setSpacing(8)

                lbl = QLabel(ip)
                lbl.setStyleSheet(
                    "font: 600 13px 'Consolas', 'Segoe UI'; color: #111;"
                    " background: transparent;"
                )
                row_h.addWidget(lbl)
                row_h.addStretch()

                btn_use = QPushButton('→ Use')
                btn_use.setFixedHeight(30)
                btn_use.setFixedWidth(84)
                btn_use.setStyleSheet(primary_button_qss(radius=7, font_px=12))

                def _on_use(_=False, _ip=ip, _b=btn_use):
                    _atem_use_ip(_ip)
                    _b.setText('✓ Set')
                    _b.setEnabled(False)

                btn_use.clicked.connect(_on_use)
                row_h.addWidget(btn_use)

                atem_disc_layout.addWidget(row_w)

            atem_disc_scroll.setFixedHeight(min(len(found), 4) * 42)

        btn_atem_discover.setEnabled(True)
        btn_atem_discover.setText('Discover switchers')

    class _AtemDiscSignal(QObject):
        finished = pyqtSignal(object)

    dialog._atem_disc_sig = _AtemDiscSignal()

    def _on_atem_disc_finished(found):
        if not dialog.isVisible():
            return
        _atem_show_results(found)

    dialog._atem_disc_sig.finished.connect(_on_atem_disc_finished)

    def _run_atem_disc():
        from application.camera_discovery import discover_atem_switchers
        import logging as _logging
        try:
            found = discover_atem_switchers()
        except Exception as exc:  # noqa: BLE001
            _logging.getLogger(__name__).error("ATEM discovery failed: %s", exc)
            found = []
        dialog._atem_disc_sig.finished.emit(found)

    def _on_atem_discover_clicked():
        _atem_clear_results()
        atem_disc_scroll.setFixedHeight(0)
        atem_disc_status.setText('Scanning network for ATEM switchers…')
        btn_atem_discover.setEnabled(False)
        btn_atem_discover.setText('Scanning…')
        threading.Thread(target=_run_atem_disc, daemon=True).start()

    btn_atem_discover.clicked.connect(_on_atem_discover_clicked)
    # Assigning an IP is locked during a live session, same as the IP edit.
    dialog._lock_if_live(btn_atem_discover, is_on,
                       'Stop the session before changing the ATEM IP')

    # Separator before the connection-status section
    _atem_sep_disc = QFrame()
    _atem_sep_disc.setFrameShape(QFrame.HLine)
    _atem_sep_disc.setFixedHeight(1)
    _atem_sep_disc.setStyleSheet("background: #F0F1EE; border: none;")
    layout.addWidget(_atem_sep_disc)

    # ── Estado ATEM actual ────────────────────────────────────────────────
    from domain.atem_state import ATEMState as _ATEMState

    _STATE_STYLE = {
        _ATEMState.CONNECTED:          ('ok',      '● Connected'),
        _ATEMState.CONNECTING:         ('warn',    '● Connecting…'),
        _ATEMState.RECONNECTING:       ('warn',    '● Reconnecting…'),
        _ATEMState.DISCONNECTED:       ('error',   '● Disconnected'),
        _ATEMState.ERROR:              ('error',   '● Error'),
        _ATEMState.NOT_CONFIGURED:     ('neutral', '● Not configured'),
        _ATEMState.DEPENDENCY_MISSING: ('neutral', '● Library missing'),
    }

    _mon = getattr(mw, '_atem_monitor', None)
    _cur_state = getattr(_mon, 'state', None)

    def _atem_status_values(state):
        return _STATE_STYLE.get(state, ('neutral', '● Unknown'))

    _atem_pill_state, _atem_pill_text = _atem_status_values(_cur_state)
    atem_status_pill = dialog._status_pill(_atem_pill_text, state=_atem_pill_state)
    layout.addWidget(atem_status_pill)

    # ── Last ATEM error ───────────────────────────────────────────────────
    _init_error = getattr(_mon, 'last_error', '')
    last_error_lbl = QLabel(f'Last error: {_init_error}' if _init_error else '')
    last_error_lbl.setStyleSheet(
        f"font: 11px 'Inter Tight', 'Segoe UI'; color: {_C_ERROR};"
    )
    last_error_lbl.setWordWrap(True)
    last_error_lbl.setVisible(bool(_init_error))
    layout.addWidget(last_error_lbl)

    # ── Botón Reconnect ATEM ──────────────────────────────────────────────
    btn_reconnect = dialog._btn('Reconnect ATEM', variant='ghost', icon='refresh')

    def _set_atem_status(state):
        kind, text = _atem_status_values(state)
        _pill_map = {
            'ok':      (_C_SUCCESS_BG,  _C_SUCCESS_BD,  _C_SUCCESS,   'green'),
            'warn':    (_C_WARNING_BG,  _C_WARNING_BD,  _C_WARNING,   'amber'),
            'error':   (_C_ERROR_BG,    _C_ERROR_BD,    _C_ERROR,     'red'),
            'neutral': ('#F4F5F3',      '#E6E8E5',      _C_SECONDARY, 'off'),
        }
        bg, bd, fg, led_state = _pill_map.get(kind, _pill_map['neutral'])
        # _status_pill devuelve un QWidget contenedor — actualizar hijos.
        atem_status_pill.setStyleSheet(
            f"background: {bg}; border: 1px solid {bd}; border-radius: 8px;"
        )
        from PyQt5.QtWidgets import QLabel as _QLabel
        led = atem_status_pill.findChild(_QLabel, 'led_dot')
        if led:
            dialog._set_led(led, led_state)
        text_labels = [lb for lb in atem_status_pill.findChildren(_QLabel)
                       if lb.objectName() != 'led_dot']
        if text_labels:
            text_labels[0].setText(text)
            text_labels[0].setStyleSheet(
                f"font: 600 13px 'Inter Tight', 'Segoe UI';"
                f" color: {fg}; background: transparent;"
            )

    def _on_reconnect():
        btn_reconnect.setEnabled(False)
        btn_reconnect.setText('Reconnecting…')
        last_error_lbl.setVisible(False)
        mw._do_restart_atem_monitor()
        _set_atem_status(_ATEMState.CONNECTING)

    def _on_dialog_atem_state(state):
        _set_atem_status(state)
        btn_reconnect.setEnabled(True)
        btn_reconnect.setText('Reconnect ATEM')
        err = getattr(getattr(mw, '_atem_monitor', None), 'last_error', '')
        last_error_lbl.setText(f'Last error: {err}' if err else '')
        last_error_lbl.setVisible(bool(err))

    btn_reconnect.clicked.connect(_on_reconnect)
    mw.atem_state_changed.connect(_on_dialog_atem_state)
    def _on_dialog_destroyed(_=None) -> None:
        try:
            dialog._disconnect_signal(mw.atem_state_changed, _on_dialog_atem_state)
        except RuntimeError:
            pass  # mw already deleted during app shutdown

    dialog.destroyed.connect(_on_dialog_destroyed)

    # ── Botón Scan ATEM ────────────────────────────────────────────────────
    # Quick reachability probe of the *configured* ATEM IP (TCP 9910, same
    # convention as the Test tab), run off the GUI thread. If reachable it
    # kicks a monitor restart so the link is confirmed; otherwise it reports
    # the failure. Disabled when no ATEM IP is configured — nothing to scan.
    from config import is_valid_ip as _is_valid_ip_atem
    btn_scan_atem = dialog._btn('Scan', variant='ghost', icon='search')

    class _AtemScanSignal(QObject):
        done = pyqtSignal(bool)

    dialog._atem_scan_sig = _AtemScanSignal()

    def _apply_atem_scan(ok: bool):
        btn_scan_atem.setEnabled(True)
        btn_scan_atem.setText('Scan')
        if ok:
            last_error_lbl.setVisible(False)
            mw._do_restart_atem_monitor()
            _set_atem_status(_ATEMState.CONNECTING)
        else:
            _set_atem_status(_ATEMState.DISCONNECTED)
            import config as _cfg_scan
            last_error_lbl.setText(
                f'Last error: No response from {_cfg_scan.ATEM.ip}:9910'
            )
            last_error_lbl.setVisible(True)

    dialog._atem_scan_sig.done.connect(_apply_atem_scan)

    def _scan_atem_worker():
        import config as _cfg_scan
        if sim_active:
            ok = True
        else:
            try:
                with socket.create_connection((_cfg_scan.ATEM.ip, 9910), timeout=3):
                    ok = True
            except OSError as exc:
                import logging as _log
                _log.getLogger(__name__).warning("ATEM scan failed: %s", exc)
                ok = False
        dialog._atem_scan_sig.done.emit(ok)

    def _on_scan_atem():
        btn_scan_atem.setEnabled(False)
        btn_scan_atem.setText('Scanning…')
        _set_atem_status(_ATEMState.CONNECTING)
        threading.Thread(target=_scan_atem_worker, daemon=True).start()

    btn_scan_atem.clicked.connect(_on_scan_atem)
    if not _is_valid_ip_atem(ATEM.ip):
        btn_scan_atem.setEnabled(False)
        btn_scan_atem.setToolTip('Configure the ATEM IP first')

    _atem_btn_row = QHBoxLayout()
    _atem_btn_row.addStretch()
    _atem_btn_row.addWidget(btn_scan_atem)
    _atem_btn_row.addWidget(btn_reconnect)
    layout.addLayout(_atem_btn_row)

    # ── Botón abrir panel ATEM ────────────────────────────────────────────
    _atem_panel = getattr(mw, '_atem_panel', None)
    if _atem_panel is not None:
        _sep2 = QFrame()
        _sep2.setFrameShape(QFrame.HLine)
        _sep2.setFixedHeight(1)
        _sep2.setStyleSheet("background: #F0F1EE; border: none;")
        layout.addWidget(_sep2)

        btn_open_panel = dialog._btn('ATEM Control Panel  →', variant='primary', icon='monitor')
        btn_open_panel.setToolTip('Open the ATEM switcher control buttons')

        def _on_open_atem_panel():
            mw._toggle_atem_panel()
            dialog.accept()

        btn_open_panel.clicked.connect(_on_open_atem_panel)
        layout.addWidget(btn_open_panel, 0, Qt.AlignRight)

    # ── Automatización ATEM ───────────────────────────────────────────────
    layout = panel_layout(_atem_col2_l, 'ATEM Automation')
    build_atem_automation_section(dialog, layout, mw)

    atem_layout.addStretch()
