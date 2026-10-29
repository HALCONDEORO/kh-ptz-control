#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_schedule_dialog.py — Unit tests for ScheduleDialog._save() error feedback (#198).

No QApplication required — Qt symbols are injected into whatever stub
PyQt5.QtWidgets already has in sys.modules (safe with other stub-based test
files that run before this one in a full pytest session).
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


# ── Ensure the Qt stubs have the symbols schedule_dialog needs ────────────────

class _FakeQDialog:
    def __init__(self, parent=None):
        pass


def _ensure_qt_stubs() -> None:
    """Inject minimal Qt symbols into sys.modules stubs (or create them)."""
    for mod_name in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    qtc = sys.modules["PyQt5.QtCore"]
    if not hasattr(qtc, "Qt"):
        qtc.Qt = MagicMock()
    if not hasattr(qtc, "QTime"):
        qtc.QTime = MagicMock()

    qtw = sys.modules["PyQt5.QtWidgets"]
    _defaults = {
        "QDialog":     _FakeQDialog,
        "QVBoxLayout": MagicMock(return_value=MagicMock()),
        "QHBoxLayout": MagicMock(return_value=MagicMock()),
        "QLabel":      MagicMock,
        "QCheckBox":   MagicMock,
        "QTimeEdit":   MagicMock,
        "QPushButton": MagicMock,
        "QFrame":      MagicMock,
        "QWidget":     MagicMock,
        "QMessageBox": MagicMock(),
    }
    for name, value in _defaults.items():
        if not hasattr(qtw, name):
            setattr(qtw, name, value)


_ensure_qt_stubs()

import ui.schedule_dialog as sd  # noqa: E402  (must follow stub setup)


# ── Test helpers ──────────────────────────────────────────────────────────────

def _make_row():
    """Fake (checkbox, t_start, t_end) matching the real widget protocol."""
    chk = MagicMock()
    chk.isChecked.return_value = True
    t_start = MagicMock()
    t_start.time.return_value.toString.return_value = "09:00"
    t_end = MagicMock()
    t_end.time.return_value.toString.return_value = "17:00"
    return chk, t_start, t_end


class _FakeDialog(sd.ScheduleDialog):
    """ScheduleDialog with Qt __init__ bypassed — _rows wired directly."""

    def __init__(self):
        from application.schedule_config import DAYS
        self._rows = {day: _make_row() for day in DAYS}
        self._always_bypass = False   # añadido por always_bypass feature


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestSaveSuccess:

    def test_accept_called_when_save_succeeds(self):
        dlg = _FakeDialog()
        dlg.accept = MagicMock()
        with patch("ui.schedule_dialog.save_schedule", return_value=True):
            dlg._save()
        dlg.accept.assert_called_once()

    def test_no_warning_shown_on_success(self):
        dlg = _FakeDialog()
        dlg.accept = MagicMock()
        with patch("ui.schedule_dialog.save_schedule", return_value=True), \
             patch("ui.schedule_dialog.QMessageBox") as mock_mb:
            dlg._save()
        mock_mb.warning.assert_not_called()


class TestSaveFailure:

    def test_accept_not_called_when_save_fails(self):
        dlg = _FakeDialog()
        dlg.accept = MagicMock()
        with patch("ui.schedule_dialog.save_schedule", return_value=False), \
             patch("ui.schedule_dialog.QMessageBox"):
            dlg._save()
        dlg.accept.assert_not_called()

    def test_warning_shown_when_save_fails(self):
        dlg = _FakeDialog()
        dlg.accept = MagicMock()
        with patch("ui.schedule_dialog.save_schedule", return_value=False), \
             patch("ui.schedule_dialog.QMessageBox") as mock_mb:
            dlg._save()
        mock_mb.warning.assert_called_once()

    def test_warning_message_mentions_failure(self):
        dlg = _FakeDialog()
        dlg.accept = MagicMock()
        with patch("ui.schedule_dialog.save_schedule", return_value=False), \
             patch("ui.schedule_dialog.QMessageBox") as mock_mb:
            dlg._save()
        args = mock_mb.warning.call_args[0]
        message_body = args[2].lower()
        assert any(word in message_body for word in ("fail", "save", "error", "could not"))

    def test_warning_first_arg_is_dialog_itself(self):
        dlg = _FakeDialog()
        dlg.accept = MagicMock()
        with patch("ui.schedule_dialog.save_schedule", return_value=False), \
             patch("ui.schedule_dialog.QMessageBox") as mock_mb:
            dlg._save()
        parent_arg = mock_mb.warning.call_args[0][0]
        assert parent_arg is dlg
