# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/test_tab.py — ConfigDialog "Test" tab (in-app diagnostics) (#894 phase 1)
#
# Read-only page: runs the same checks as `khptz doctor` from the touchscreen.
# Extracted verbatim from ConfigDialog._build_ui; `self` -> `dialog`, and the
# _build_ui-local _panel_layout helper is received as a parameter.

from __future__ import annotations

import threading

from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel

from ui.styles import CARD_BD as _C_CARD_BD, FIELD_BG as _C_FIELD_BG, MUTED as _C_MUTED


def build_test_tab(dialog, tools_layout, panel_layout):
    """Populate the Test tab with the in-app System Diagnostics panel."""
    # ── Test tab: System Diagnostics ──────────────────────────────────
    # Runs the same checks as `khptz doctor` from the touchscreen so a
    # technician never needs a terminal in the field. Checks run in a
    # worker thread (network reachability can block) and the result is
    # marshalled back to the GUI thread via a queued signal — same pattern
    # as the camera scan above.
    diag_layout = panel_layout(
        tools_layout, 'System Diagnostics',
        badge_text='doctor', badge_kind='muted',
    )
    diag_status = QLabel('Run the built-in health checks to see system status.')
    diag_status.setWordWrap(True)
    diag_status.setStyleSheet(
        f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_MUTED};"
        " background: transparent;"
    )
    diag_layout.addWidget(diag_status)

    diag_results = QLabel('')
    diag_results.setWordWrap(True)
    diag_results.setTextInteractionFlags(Qt.TextSelectableByMouse)
    diag_results.setVisible(False)
    diag_results.setStyleSheet(
        "font: 12px 'Consolas', 'Courier New', monospace; color: #111;"
        f" background: {_C_FIELD_BG}; border: 1px solid {_C_CARD_BD};"
        " border-radius: 8px; padding: 8px 10px;"
    )
    diag_layout.addWidget(diag_results)

    btn_diag = dialog._btn('Run Diagnostics', variant='primary', icon='search')
    diag_layout.addWidget(btn_diag, 0, Qt.AlignRight)

    class _DiagSignals(QObject):
        finished = pyqtSignal(object)

    _diag_sig = _DiagSignals()

    def _on_diag_finished(view):
        if not dialog.isVisible():
            return
        btn_diag.setEnabled(True)
        btn_diag.setText('Run Diagnostics')
        if view is None:
            diag_status.setText('Diagnostics failed to run — see logs.')
            diag_results.setVisible(False)
            return
        diag_status.setText(f'Overall: {view.overall}  ·  {view.summary}')
        diag_results.setText('\n'.join(view.text_lines))
        diag_results.setVisible(True)

    _diag_sig.finished.connect(_on_diag_finished)

    def _run_diag():
        import logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            import os as _os
            from domain.runtime_mode import RuntimeMode
            from application.diagnostics_service import DiagnosticsService
            from application.diagnostics_presenter import build_view
            try:
                mode = RuntimeMode(_os.environ.get('KHPTZ_PROFILE', 'production'))
            except ValueError:
                mode = RuntimeMode.PRODUCTION
            view = build_view(DiagnosticsService(mode=mode).run())
        except Exception as exc:  # noqa: BLE001
            _log.error("In-app diagnostics failed: %s", exc)
            view = None
        _diag_sig.finished.emit(view)

    def _on_diag_clicked():
        diag_status.setText('Running diagnostics…')
        diag_results.setVisible(False)
        btn_diag.setEnabled(False)
        btn_diag.setText('Running…')
        threading.Thread(target=_run_diag, daemon=True).start()

    btn_diag.clicked.connect(_on_diag_clicked)
