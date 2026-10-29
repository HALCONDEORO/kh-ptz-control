# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""State policy for the main-window ATEM button and its status dot.

Extracted from MainWindow (god-object ratchet) so the demo/sim branch can
grow honest behaviour without growing main_window.py.
"""

import logging

from domain.atem_state import ATEMState

logger = logging.getLogger(__name__)

_DOT_GREEN = "background: #2e7d32; border-radius: 6px;"
_DOT_RED = "background: #c62828; border-radius: 6px;"


def apply_atem_button_state(btn, dot, panel, state, fake_atem) -> None:
    """Apply the ATEM connection state to the button, dot and panel.

    Demo/sim (fake_atem present): the dot reflects the FakeATEM's real
    connection state, but the button stays enabled and the panel stays
    open when disconnected — otherwise the operator could not reach the
    panel's Reconnect button (found in review of #921). Real hardware
    keeps the strict behaviour: disabled button, panel force-hidden.
    """
    if fake_atem is not None:
        connected = fake_atem.get_status().connected
    else:
        connected = (state == ATEMState.CONNECTED)
    if connected:
        dot.setStyleSheet(_DOT_GREEN)
        btn.setEnabled(True)
        btn.setToolTip("ATEM switcher panel — conectado")
        return
    dot.setStyleSheet(_DOT_RED)
    if fake_atem is not None:
        btn.setEnabled(True)
        btn.setToolTip("ATEM virtual desconectado — Reconnect en el panel")
        return
    btn.setEnabled(False)
    btn.setToolTip(f"ATEM no disponible — {state.name if state else 'desconocido'}")
    if btn.isChecked():
        btn.setChecked(False)
        if panel is not None:
            panel.hide()
