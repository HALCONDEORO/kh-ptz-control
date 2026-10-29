#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# screen_off_dialog.py — Countdown dialog shown when the screen turns off

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

_COUNTDOWN_SECS = 30


class ScreenOffDialog(QDialog):
    """Asks the operator whether to power off cameras when the screen turns off.

    Auto-accepts (cameras off) after COUNTDOWN_SECS seconds with no response.
    Closing with X is treated as No (session continues, screen stays on).
    """

    def __init__(self, parent=None, timeout_secs: int = _COUNTDOWN_SECS):
        super().__init__(parent)
        self._remaining = timeout_secs

        self.setWindowTitle("Screen turned off")
        self.setWindowFlags(
            Qt.Dialog | Qt.WindowStaysOnTopHint
            | Qt.CustomizeWindowHint | Qt.WindowTitleHint
        )
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 20, 24, 20)

        self._msg = QLabel("Do you want to power off the cameras?")
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setStyleSheet("font: bold 15px;")
        layout.addWidget(self._msg)

        self._countdown = QLabel(self._countdown_text())
        self._countdown.setAlignment(Qt.AlignCenter)
        self._countdown.setStyleSheet("font: 12px; color: #888;")
        layout.addWidget(self._countdown)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._btn_yes = QPushButton("Yes — Power off")
        self._btn_yes.setStyleSheet(
            "QPushButton { background: #8b1a1a; color: white; font: bold 13px;"
            " border-radius: 6px; padding: 8px 20px; }"
            "QPushButton:pressed { background: #5a0d0d; }"
        )
        self._btn_yes.clicked.connect(self.accept)

        self._btn_no = QPushButton("No — Keep on")
        self._btn_no.setStyleSheet(
            "QPushButton { background: #1a4a1a; color: white; font: bold 13px;"
            " border-radius: 6px; padding: 8px 20px; }"
            "QPushButton:pressed { background: #0d2f0d; }"
        )
        self._btn_no.clicked.connect(self.reject)

        btn_row.addWidget(self._btn_yes)
        btn_row.addWidget(self._btn_no)
        layout.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _countdown_text(self) -> str:
        return f"Auto power-off in {self._remaining}s…"

    def _tick(self) -> None:
        self._remaining -= 1
        self._countdown.setText(self._countdown_text())
        if self._remaining <= 0:
            self._timer.stop()
            self.accept()

    def closeEvent(self, event):
        # X button → No: stop timer so it doesn't fire after dialog is gone
        self._timer.stop()
        self.reject()
        event.accept()
