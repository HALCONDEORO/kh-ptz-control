#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""test_change_password_dialog.py — ChangePasswordDialog._validate dispatch.

The dialog is target-aware (operator entry vs administrator). _validate is
exercised as an unbound function with a MagicMock self, so no QApplication is
needed; Qt is stubbed before import. The point under test is that the current
password is verified through the right central-auth function for the target.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _ensure_qt() -> None:
    """Make ui.dialogs_mixin importable with the real PyQt5.

    A sibling test may have injected a *bare* PyQt5 stub (missing symbols like
    QInputDialog) into sys.modules during collection. Drop any such stub and load
    the genuine PyQt5 (available offscreen in this project), exactly as
    test_setup_wizard does — this keeps the import clean and, crucially, leaves no
    MagicMock junk in sys.modules that would poison later Qt tests
    (e.g. test_schedule_dialog). Fall back to a complete stub only if PyQt5 is
    genuinely unavailable (lean CI).
    """
    for name in ("PyQt5.QtWidgets", "PyQt5.QtGui", "PyQt5.QtCore", "PyQt5"):
        mod = sys.modules.get(name)
        if mod is not None and getattr(mod, "__file__", None) is None:
            sys.modules.pop(name, None)  # bare ModuleType stub → drop it
    try:
        import PyQt5.QtWidgets  # noqa: F401  (force the real import)
        return
    except ImportError:
        pass
    for mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui"):
        sys.modules.setdefault(mod, types.ModuleType(mod))
    qtc = sys.modules["PyQt5.QtCore"]
    if not hasattr(qtc, "Qt"):
        qtc.Qt = MagicMock()
    qtw = sys.modules["PyQt5.QtWidgets"]
    for a in ("QMessageBox", "QInputDialog", "QDialog", "QVBoxLayout",
              "QFormLayout", "QHBoxLayout", "QLabel", "QLineEdit", "QPushButton"):
        if not hasattr(qtw, a):
            setattr(qtw, a, MagicMock)


_ensure_qt()

import ui.dialogs_mixin as _dm  # noqa: E402


def _stub(target: str, cur="cur", new="new", confirm="new") -> MagicMock:
    stub = MagicMock()
    stub._target = target
    stub._cur.text.return_value = cur
    stub._new.text.return_value = new
    stub._confirm.text.return_value = confirm
    stub.new_password = ""
    return stub


class TestValidateDispatch:

    def test_entry_target_uses_verify_entry(self):
        stub = _stub("entry")
        with patch("application.authentication.verify_entry", return_value=True) as ve, \
             patch("application.authentication.verify_admin", return_value=False) as va:
            _dm.ChangePasswordDialog._validate(stub)
        ve.assert_called_once_with("cur")
        va.assert_not_called()
        stub.accept.assert_called_once()
        assert stub.new_password == "new"

    def test_admin_target_uses_verify_admin(self):
        stub = _stub("admin")
        with patch("application.authentication.verify_entry", return_value=False) as ve, \
             patch("application.authentication.verify_admin", return_value=True) as va:
            _dm.ChangePasswordDialog._validate(stub)
        va.assert_called_once_with("cur")
        ve.assert_not_called()
        stub.accept.assert_called_once()


class TestValidateGuards:

    def test_wrong_current_blocks(self):
        stub = _stub("entry")
        with patch("application.authentication.verify_entry", return_value=False):
            _dm.ChangePasswordDialog._validate(stub)
        stub.accept.assert_not_called()
        stub._err.setText.assert_called()

    def test_mismatch_new_blocks(self):
        stub = _stub("entry", new="a", confirm="b")
        with patch("application.authentication.verify_entry", return_value=True):
            _dm.ChangePasswordDialog._validate(stub)
        stub.accept.assert_not_called()

    def test_empty_field_blocks(self):
        stub = _stub("entry", cur="")
        with patch("application.authentication.verify_entry", return_value=True) as ve:
            _dm.ChangePasswordDialog._validate(stub)
        ve.assert_not_called()  # short-circuits before verification
        stub.accept.assert_not_called()


class TestResetWithoutCurrent:
    """require_current=False: no 'Current' field, no verification (reset flow)."""

    def test_accepts_without_verifying_current(self):
        stub = _stub("entry", cur="ignored")
        stub._require_current = False
        with patch("application.authentication.verify_entry") as ve, \
             patch("application.authentication.verify_admin") as va:
            _dm.ChangePasswordDialog._validate(stub)
        ve.assert_not_called()
        va.assert_not_called()
        stub.accept.assert_called_once()
        assert stub.new_password == "new"

    def test_mismatch_still_blocks(self):
        stub = _stub("admin", new="a", confirm="b")
        stub._require_current = False
        _dm.ChangePasswordDialog._validate(stub)
        stub.accept.assert_not_called()

    def test_empty_new_still_blocks(self):
        stub = _stub("admin", new="")
        stub._require_current = False
        _dm.ChangePasswordDialog._validate(stub)
        stub.accept.assert_not_called()


class TestRequireCurrentPolicy:
    """Who must type the current password: only when changing your OWN one.

    Supercore (master) never needs it; an admin resets the operator password
    freely but must confirm the current admin password to change its own.
    """

    @pytest.mark.parametrize("is_supercore,target,expected", [
        (True,  "admin", False),   # supercore → master, no current
        (True,  "entry", False),
        (False, "entry", False),   # admin resets operator pw freely
        (False, "admin", True),    # admin changing its OWN pw → current required
    ])
    def test_current_required_only_for_own_admin_password(
        self, is_supercore, target, expected
    ):
        win = MagicMock()
        win._session_is_supercore = is_supercore
        ctrl = _dm.DialogsController(win)

        captured = {}

        class _FakeDlg:
            def __init__(self, parent, target, require_current):
                captured["require_current"] = require_current

            def exec_(self):
                return 0  # rejected → skip persistence branch

        with patch.object(_dm, "ChangePasswordDialog", _FakeDlg):
            ctrl._change_password(target)
        assert captured["require_current"] is expected
