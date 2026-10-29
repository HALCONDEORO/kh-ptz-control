#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_virtual_keyboard.py — Pruebas de seguridad cuando se destruye el target (#199).

Las pruebas se ejecutan sin una QApplication real. Las clases Qt se sustituyen
por stubs para que toda la interacción pase por la lógica del teclado.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


# ── Qt stubs ─────────────────────────────────────────────────────────────────

def _ensure_qt_stubs() -> None:
    for mod_name in ("PyQt5", "PyQt5.QtWidgets", "PyQt5.QtCore"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    qtc = sys.modules["PyQt5.QtCore"]
    if not hasattr(qtc, "Qt"):
        qtc.Qt = MagicMock()
    if not hasattr(qtc, "QObject"):
        qtc.QObject = object
    if not hasattr(qtc, "QEvent"):
        qtc.QEvent = MagicMock()
    if not hasattr(qtc, "QTimer"):
        qtc.QTimer = MagicMock()

    qtw = sys.modules["PyQt5.QtWidgets"]
    # QWidget and QLineEdit must be plain object so VirtualKeyboard (which inherits
    # from QWidget) is a normal Python class — force-set regardless of prior stubs.
    qtw.QWidget = object
    qtw.QLineEdit = object
    _defaults = {
        "QPushButton":  MagicMock,
        "QVBoxLayout":  MagicMock,
        "QHBoxLayout":  MagicMock,
        "QApplication": MagicMock(),
        "QSizePolicy":  MagicMock(),
    }
    for name, value in _defaults.items():
        if not hasattr(qtw, name):
            setattr(qtw, name, value)


_ensure_qt_stubs()

import importlib
import ui.virtual_keyboard as vk  # noqa: E402
# Re-import so VirtualKeyboard picks up our QWidget=object stub even if another
# test file already cached the module with a different QWidget base class.
vk = importlib.reload(vk)


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeLineEdit:
    """Stub minimo de QLineEdit con una senal destroyed simulada."""

    def __init__(self):
        self.destroyed = MagicMock()
        self.destroyed.connect = MagicMock()
        self.destroyed.disconnect = MagicMock()
        self._text = ""
        self.returnPressed = MagicMock()

    def insert(self, char: str) -> None:
        self._text += char

    def backspace(self) -> None:
        self._text = self._text[:-1]


def _make_keyboard() -> vk.VirtualKeyboard:
    """Crea un VirtualKeyboard sin construir UI real."""
    kb = object.__new__(vk.VirtualKeyboard)
    kb._target = None
    kb._shift = False
    kb._letter_btns = {}
    kb._shift_btn = None
    kb._visible = False
    kb.hide = MagicMock()
    kb.isVisible = MagicMock(return_value=False)
    kb.show = MagicMock()
    kb._reposition = MagicMock()
    return kb


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestShowForConnectsDestroyedSignal:

    def test_show_for_connects_destroyed_to_clear_target(self):
        kb = _make_keyboard()
        widget = _FakeLineEdit()

        kb.show_for(widget)

        widget.destroyed.connect.assert_called_once_with(kb._clear_target)

    def test_show_for_disconnects_previous_target_before_connecting_new(self):
        kb = _make_keyboard()
        first = _FakeLineEdit()
        second = _FakeLineEdit()

        kb.show_for(first)
        kb.show_for(second)

        first.destroyed.disconnect.assert_called_once_with(kb._clear_target)
        second.destroyed.connect.assert_called_once_with(kb._clear_target)

    def test_show_for_tolerates_disconnect_error_on_deleted_previous(self):
        kb = _make_keyboard()
        first = _FakeLineEdit()
        first.destroyed.disconnect.side_effect = RuntimeError("deleted")
        second = _FakeLineEdit()

        kb.show_for(first)
        kb.show_for(second)  # must not raise

        assert kb._target is second


class TestClearTarget:

    def test_clear_target_sets_target_to_none(self):
        kb = _make_keyboard()
        kb._target = _FakeLineEdit()

        kb._clear_target()

        assert kb._target is None

    def test_clear_target_hides_keyboard(self):
        kb = _make_keyboard()
        kb._target = _FakeLineEdit()

        kb._clear_target()

        kb.hide.assert_called_once()


class TestOnKeyWithDeletedTarget:

    def test_on_key_character_catches_runtime_error_and_clears_target(self):
        kb = _make_keyboard()
        widget = _FakeLineEdit()
        widget.insert = MagicMock(side_effect=RuntimeError("wrapped C/C++ object deleted"))
        kb._target = widget

        kb._on_key("a")  # must not raise

        assert kb._target is None

    def test_on_key_backspace_catches_runtime_error_and_clears_target(self):
        kb = _make_keyboard()
        widget = _FakeLineEdit()
        widget.backspace = MagicMock(side_effect=RuntimeError("wrapped C/C++ object deleted"))
        kb._target = widget

        kb._on_key("⌫")  # must not raise

        assert kb._target is None

    def test_on_key_enter_catches_runtime_error_and_clears_target(self):
        kb = _make_keyboard()
        widget = _FakeLineEdit()
        widget.returnPressed = MagicMock()
        widget.returnPressed.emit = MagicMock(side_effect=RuntimeError("deleted"))
        kb._target = widget

        kb._on_key("↵")  # must not raise

        assert kb._target is None

    def test_on_key_with_no_target_is_silent(self):
        kb = _make_keyboard()
        kb._target = None

        kb._on_key("a")  # must not raise


class TestOnKeyNormalOperation:

    def test_character_is_inserted_into_target(self):
        kb = _make_keyboard()
        widget = _FakeLineEdit()
        kb._target = widget

        kb._on_key("h")
        kb._on_key("i")

        assert widget._text == "hi"

    def test_backspace_removes_last_character(self):
        kb = _make_keyboard()
        widget = _FakeLineEdit()
        widget._text = "abc"
        kb._target = widget

        kb._on_key("⌫")

        assert widget._text == "ab"

    def test_enter_emits_returnPressed_and_hides(self):
        kb = _make_keyboard()
        widget = _FakeLineEdit()
        kb._target = widget

        kb._on_key("↵")

        widget.returnPressed.emit.assert_called_once()
        kb.hide.assert_called_once()
