# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from pathlib import Path
from conftest import ensure_real_qt


def test_indicator_retains_warning_until_same_path_confirmed():
    ensure_real_qt()
    from PyQt5.QtWidgets import QApplication
    from core.persistence_status import PersistenceStatus
    from ui.persistence_indicator import PersistenceIndicator
    app = QApplication.instance() or QApplication([])
    state = PersistenceStatus()
    widget = PersistenceIndicator(source=state)
    assert "none this session" in widget.text()
    state.record(Path("private_filename"), confirmed=False)
    state.record(Path("another"), confirmed=True)
    widget.refresh()
    assert "FAILED / UNCONFIRMED" in widget.text()
    assert "private_filename" not in widget.text()
    state.record(Path("private_filename"), confirmed=True)
    widget.refresh()
    assert "FAILED" not in widget.text()
    assert widget.accessibleName() == "Persistence status"
    widget.close()
    widget.deleteLater()
    app.processEvents()
