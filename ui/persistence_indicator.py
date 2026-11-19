# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Read-only session receipt indicator; UI updates stay on the Qt thread."""
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QLabel
from core.persistence_status import status, observer_failed


class PersistenceIndicator(QLabel):
    def __init__(self, parent=None, *, source=status):
        super().__init__(parent)
        self._source = source
        self.setAccessibleName("Persistence status")
        self.setToolTip("This session only. Covers shared JSON and atomic file helpers; "
                        "not camera memory or a hardware power-loss test.")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(500)
        self.refresh()

    def refresh(self):
        try:
            state = self._source.snapshot()
        except Exception:
            observer_failed.set()
            state = None
        if state is None or observer_failed.is_set():
            self.setText("SAVE STATUS UNAVAILABLE | Check logs and storage before continuing")
            self.setStyleSheet("QLabel {color: #7a1600; background: #fff0df; "
                              "border: 2px solid #9b3000; padding: 3px; font: bold 12px;}")
            return
        last = state.last_confirmed or "none this session"
        if state.unresolved_count or state.overflow:
            count = str(state.unresolved_count) + ("+" if state.overflow else "")
            self.setText(f"SAVE FAILED / UNCONFIRMED ({count}) | Last confirmed: {last}")
            self.setStyleSheet("QLabel {color: #7a1600; background: #fff0df; "
                              "border: 2px solid #9b3000; padding: 3px; font: bold 12px;}")
        else:
            self.setText(f"Last confirmed save: {last}")
            self.setStyleSheet("QLabel {color: #183c29; background: #eff7f2; "
                              "border: 1px solid #37674a; padding: 3px; font: 12px;}")


def install(window):
    """Keep the fixed-design placement out of the main window builder."""
    window._persistence_indicator = PersistenceIndicator(window)
    window._persistence_indicator.setGeometry(350, 1044, 900, 30)
