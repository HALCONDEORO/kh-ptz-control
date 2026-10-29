# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# ui/config_pages/session_tab.py — ConfigDialog "Session" tab (#894 phase 1)
#
# Start/End session with a configured-camera gate, plus the Simulation Mode
# panel. Extracted from ConfigDialog._build_ui; self -> dialog, and the local
# _panel_layout helper and the shared sim_active flag are received as params.

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from ui.config_pages.sections import build_sim_section
from ui.styles import (
    WARNING as _C_WARNING,
    WARNING_BD as _C_WARNING_BD,
    WARNING_BG as _C_WARNING_BG,
)


def build_session_tab(dialog, session_layout, mw, sim_active, panel_layout):
    """Populate the Session tab: ON/OFF gate + Simulation Mode panel."""
    layout = panel_layout(session_layout, 'Session')

    # ── Sección: Session ON / OFF ─────────────────────────────────────
    is_on   = getattr(mw, 'session_active', False)
    if is_on:
        pill_state = 'ok'
        pill_text  = 'Session running'
        pill_meta  = None
    else:
        pill_state = 'neutral'
        pill_text  = 'No session active'
        pill_meta  = None

    session_pill = dialog._status_pill(pill_text, state=pill_state, meta=pill_meta)
    layout.addWidget(session_pill)

    # Gate Start Session on having at least one configured camera. Without a
    # camera IP a session powers and queries nothing, so starting one is a
    # dead end — disable the button and point the operator to the Cameras tab.
    from config import is_valid_ip as _is_valid_ip
    import config as _cfg_cams
    cameras_configured = (
        _is_valid_ip(_cfg_cams.CAM1.ip) or _is_valid_ip(_cfg_cams.CAM2.ip)
    )

    btn_session_text = 'End Session' if is_on else 'Start Session'
    btn_session_variant = 'danger' if is_on else 'primary'
    btn_session = dialog._btn(btn_session_text, variant=btn_session_variant,
                            icon='stop' if is_on else 'play')

    if not is_on and not cameras_configured:
        btn_session.setEnabled(False)
        btn_session.setToolTip('Configure a camera IP first (Cameras tab)')
        no_cam_lbl = QLabel(
            'No camera configured — add a camera IP in the Cameras tab '
            'before starting a session.'
        )
        no_cam_lbl.setStyleSheet(
            f"font: 12px 'Inter Tight', 'Segoe UI'; color: {_C_WARNING};"
            f" background: {_C_WARNING_BG}; border: 1px solid {_C_WARNING_BD};"
            " border-radius: 8px; padding: 7px 10px;"
        )
        no_cam_lbl.setWordWrap(True)
        layout.addWidget(no_cam_lbl)

    def _on_session_btn():
        # Ending a live session is destructive — confirm with a safe default.
        if is_on and not dialog._confirm_danger(
            'End Session',
            'End the current live session?\n'
            'Cameras will stop following the program and presets.',
            'End Session',
        ):
            return
        mw._session.ToggleSession()
        dialog.accept()

    btn_session.clicked.connect(_on_session_btn)
    layout.addWidget(btn_session, 0, Qt.AlignRight)

    layout = panel_layout(session_layout, 'Simulation Mode')
    build_sim_section(dialog, layout, mw, sim_active)

    session_layout.addStretch()
