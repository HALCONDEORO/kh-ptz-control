#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_right_panel_buttons.py — Unit tests for RightPanel UI logic.

Tests run headless (no QApplication) by calling methods as unbound functions
with a MagicMock stub acting as self.  Qt modules are stubbed before import.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock



# ── Qt stubs ──────────────────────────────────────────────────────────────────

def _ensure_qt_stubs() -> None:
    for mod_name in (
        "PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets",
        "PyQt5.QtGui", "PyQt5.QtSvg",
    ):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    qtc = sys.modules["PyQt5.QtCore"]
    for attr in ("Qt", "pyqtSignal", "QTimer", "QPoint", "QMimeData", "QSize",
                 "QByteArray", "QRectF"):
        if not hasattr(qtc, attr):
            setattr(qtc, attr, MagicMock())

    # PyQt5.QtCore module alias (used as `from PyQt5 import QtCore`)
    if not hasattr(sys.modules["PyQt5"], "QtCore"):
        sys.modules["PyQt5"].QtCore = qtc  # type: ignore[attr-defined]

    qtw = sys.modules["PyQt5.QtWidgets"]
    for attr in (
        "QButtonGroup", "QFrame", "QHBoxLayout", "QLabel", "QPushButton",
        "QSlider", "QVBoxLayout", "QWidget", "QScrollArea",
        "QSizePolicy", "QAbstractItemView", "QMessageBox",
        "QListWidget", "QListWidgetItem",
    ):
        if not hasattr(qtw, attr):
            setattr(qtw, attr, MagicMock)

    qtg = sys.modules["PyQt5.QtGui"]
    for attr in ("QColor", "QPainter", "QDrag", "QPixmap", "QIcon",
                 "QPen", "QPainterPath"):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock)
    # QFont needs class-level attributes like Bold/Normal used at module level
    if not hasattr(qtg, "QFont"):
        class _FakeQFont:
            Bold = 75
            Normal = 50
            Black = 87
            def __init__(self, *args, **kwargs): pass
        qtg.QFont = _FakeQFont  # type: ignore[attr-defined]
    else:
        _qf = qtg.QFont
        if not hasattr(_qf, "Bold"):
            _qf.Bold = 75
        if not hasattr(_qf, "Normal"):
            _qf.Normal = 50
    if not hasattr(sys.modules["PyQt5"], "QtGui"):
        sys.modules["PyQt5"].QtGui = qtg  # type: ignore[attr-defined]

    qtsvg = sys.modules["PyQt5.QtSvg"]
    for attr in ("QSvgWidget", "QSvgRenderer"):
        if not hasattr(qtsvg, attr):
            setattr(qtsvg, attr, MagicMock)


_ensure_qt_stubs()

import ui.right_panel as _rp  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

_ACTIVE_FOCUS_STYLE = (
    "QPushButton { background-color: #2979D9; border: none; border-radius: 10px;"
    " font: 600 13px 'Inter Tight', 'Segoe UI'; color: white; padding: 4px 0px; }"
)
_BASE_STYLE = "base-style"


def _rp_stub(**kwargs) -> MagicMock:
    """Return a MagicMock with RightPanel-compatible attributes."""
    stub = MagicMock()
    stub._btn_focus_base_style = kwargs.get("_btn_focus_base_style", _BASE_STYLE)
    stub._atem_has_program = kwargs.get("_atem_has_program", False)
    stub._DEFAULT_ATEM_INPUT_MAP = _rp.RightPanel._DEFAULT_ATEM_INPUT_MAP
    stub._atem_input_map = dict(_rp.RightPanel._DEFAULT_ATEM_INPUT_MAP)
    stub._ON_AIR_STYLE_LIVE = "live-style"
    stub._ON_AIR_STYLE_STANDBY = "standby-style"
    return stub


# ══════════════════════════════════════════════════════════════════════════════
#  set_focus_mode
# ══════════════════════════════════════════════════════════════════════════════

class TestSetFocusMode:
    """set_focus_mode highlights the active focus button and resets the others."""

    def test_auto_activates_auto_focus_btn(self):
        stub = _rp_stub()
        _rp.RightPanel.set_focus_mode(stub, "auto")
        style = stub.btn_auto_focus.setStyleSheet.call_args[0][0]
        assert "#2979D9" in style

    def test_auto_resets_manual_to_base(self):
        stub = _rp_stub()
        _rp.RightPanel.set_focus_mode(stub, "auto")
        style = stub.btn_manual_focus.setStyleSheet.call_args[0][0]
        assert style == _BASE_STYLE

    def test_manual_activates_manual_focus_btn(self):
        stub = _rp_stub()
        _rp.RightPanel.set_focus_mode(stub, "manual")
        style = stub.btn_manual_focus.setStyleSheet.call_args[0][0]
        assert "#2979D9" in style

    def test_manual_resets_auto_to_base(self):
        stub = _rp_stub()
        _rp.RightPanel.set_focus_mode(stub, "manual")
        style = stub.btn_auto_focus.setStyleSheet.call_args[0][0]
        assert style == _BASE_STYLE

    def test_unknown_mode_resets_all_to_base(self):
        stub = _rp_stub()
        _rp.RightPanel.set_focus_mode(stub, "off")
        assert stub.btn_auto_focus.setStyleSheet.call_args[0][0] == _BASE_STYLE
        assert stub.btn_manual_focus.setStyleSheet.call_args[0][0] == _BASE_STYLE

    def test_one_push_af_always_reset_to_base(self):
        stub = _rp_stub()
        for mode in ("auto", "manual", "off"):
            stub.reset_mock()
            stub._btn_focus_base_style = _BASE_STYLE
            _rp.RightPanel.set_focus_mode(stub, mode)
            style = stub.btn_one_push_af.setStyleSheet.call_args[0][0]
            assert style == _BASE_STYLE, f"One Push AF must always reset (mode={mode!r})"


# ══════════════════════════════════════════════════════════════════════════════
#  set_exposure_level
# ══════════════════════════════════════════════════════════════════════════════

class TestSetExposureLevel:
    """set_exposure_level updates the darker/brighter button labels."""

    def test_zero_level_shows_zero(self):
        stub = _rp_stub()
        _rp.RightPanel.set_exposure_level(stub, 0)
        darker_text = stub.btn_darker.setText.call_args[0][0]
        brighter_text = stub.btn_brighter.setText.call_args[0][0]
        assert "0" in darker_text
        assert "0" in brighter_text

    def test_positive_level_shows_plus_sign(self):
        stub = _rp_stub()
        _rp.RightPanel.set_exposure_level(stub, 3)
        brighter_text = stub.btn_brighter.setText.call_args[0][0]
        assert "+3" in brighter_text

    def test_negative_level_shows_minus_sign(self):
        stub = _rp_stub()
        _rp.RightPanel.set_exposure_level(stub, -2)
        darker_text = stub.btn_darker.setText.call_args[0][0]
        # negative sign comes from int formatting, not manually added
        assert "-2" in darker_text

    def test_text_contains_darker_prefix(self):
        stub = _rp_stub()
        _rp.RightPanel.set_exposure_level(stub, 1)
        darker_text = stub.btn_darker.setText.call_args[0][0]
        assert "Darker" in darker_text

    def test_text_contains_brighter_prefix(self):
        stub = _rp_stub()
        _rp.RightPanel.set_exposure_level(stub, 1)
        brighter_text = stub.btn_brighter.setText.call_args[0][0]
        assert "Brighter" in brighter_text

    def test_both_buttons_updated(self):
        stub = _rp_stub()
        _rp.RightPanel.set_exposure_level(stub, 5)
        stub.btn_darker.setText.assert_called_once()
        stub.btn_brighter.setText.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  set_atem_state
# ══════════════════════════════════════════════════════════════════════════════

class TestSetAtemState:
    """set_atem_state controls ON AIR / home button visibility and cam indicators."""

    def _connected_state(self):
        from domain.atem_state import ATEMState
        return ATEMState.CONNECTED

    def _disconnected_state(self):
        from domain.atem_state import ATEMState
        return ATEMState.DISCONNECTED

    def test_disconnected_resets_atem_has_program(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_state(stub, self._disconnected_state())
        assert stub._atem_has_program is False

    def test_disconnected_turns_off_cam1_on_air(self):
        stub = _rp_stub()
        _rp.RightPanel.set_atem_state(stub, self._disconnected_state())
        stub._mw.Cam1.set_on_air.assert_called_with(False)

    def test_disconnected_turns_off_cam2_on_air(self):
        stub = _rp_stub()
        _rp.RightPanel.set_atem_state(stub, self._disconnected_state())
        stub._mw.Cam2.set_on_air.assert_called_with(False)

    def test_disconnected_hides_on_air_label(self):
        stub = _rp_stub(_atem_has_program=False)
        _rp.RightPanel.set_atem_state(stub, self._disconnected_state())
        # operative = False → on_air_label.setVisible(False)
        stub._on_air_label.setVisible.assert_called_with(False)

    def test_disconnected_shows_home_btn(self):
        stub = _rp_stub(_atem_has_program=False)
        _rp.RightPanel.set_atem_state(stub, self._disconnected_state())
        stub._home_btn.setVisible.assert_called_with(True)

    def test_connected_without_program_shows_home_btn(self):
        stub = _rp_stub(_atem_has_program=False)
        _rp.RightPanel.set_atem_state(stub, self._connected_state())
        # operative = connected (True) and _atem_has_program (False) = False
        stub._home_btn.setVisible.assert_called_with(True)

    def test_connected_with_program_hides_home_btn(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_state(stub, self._connected_state())
        # operative = True → home_btn.setVisible(False)
        stub._home_btn.setVisible.assert_called_with(False)

    def test_connected_with_program_shows_on_air_label(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_state(stub, self._connected_state())
        stub._on_air_label.setVisible.assert_called_with(True)


# ══════════════════════════════════════════════════════════════════════════════
#  set_atem_program
# ══════════════════════════════════════════════════════════════════════════════

class TestSetAtemProgram:
    """set_atem_program maps ATEM input numbers to labels and camera ON AIR state."""

    def test_input_2_sets_platform_label(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 2)
        text = stub._on_air_label.setText.call_args[0][0]
        assert "Platform" in text

    def test_input_3_sets_comments_label(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 3)
        text = stub._on_air_label.setText.call_args[0][0]
        assert "Comments" in text

    def test_input_1_sets_pc_label(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 1)
        text = stub._on_air_label.setText.call_args[0][0]
        assert "PC" in text or "ON AIR" in text

    def test_input_4_none_label_shows_on_air_none(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 4)
        text = stub._on_air_label.setText.call_args[0][0]
        # Input 4 maps to ("None", 0) → "● ON AIR — None"
        label = _rp.RightPanel._DEFAULT_ATEM_INPUT_MAP[4][0]
        assert label in text and "ON AIR" in text

    def test_unknown_input_sets_standby_label(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 99)
        text = stub._on_air_label.setText.call_args[0][0]
        assert "STANDBY" in text

    def test_input_2_platform_cam1_on_air(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 2)
        stub._mw.Cam1.set_on_air.assert_called_with(True)
        stub._mw.Cam2.set_on_air.assert_called_with(False)

    def test_input_3_comments_cam2_on_air(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 3)
        stub._mw.Cam1.set_on_air.assert_called_with(False)
        stub._mw.Cam2.set_on_air.assert_called_with(True)

    def test_input_1_neither_cam_on_air(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 1)
        stub._mw.Cam1.set_on_air.assert_called_with(False)
        stub._mw.Cam2.set_on_air.assert_called_with(False)

    def test_first_program_sets_has_program_true(self):
        stub = _rp_stub(_atem_has_program=False)
        _rp.RightPanel.set_atem_program(stub, 2)
        assert stub._atem_has_program is True

    def test_first_program_shows_on_air_label(self):
        stub = _rp_stub(_atem_has_program=False)
        _rp.RightPanel.set_atem_program(stub, 2)
        stub._on_air_label.setVisible.assert_called_with(True)

    def test_first_program_hides_home_btn(self):
        stub = _rp_stub(_atem_has_program=False)
        _rp.RightPanel.set_atem_program(stub, 2)
        stub._home_btn.setVisible.assert_called_with(False)

    def test_subsequent_program_does_not_call_set_visible_again(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_program(stub, 2)
        stub._on_air_label.setVisible.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
#  set_atem_input_names
# ══════════════════════════════════════════════════════════════════════════════

class TestSetAtemInputNames:
    """set_atem_input_names updates labels from the real ATEM while preserving cam_key."""

    def test_updates_label_for_known_input(self):
        stub = _rp_stub()
        _rp.RightPanel.set_atem_input_names(stub, {2: "Platform Camera HD"})
        label, _ = stub._atem_input_map[2]
        assert label == "Platform Camera HD"

    def test_preserves_cam_key_for_known_input(self):
        stub = _rp_stub()
        original_cam_key = stub._atem_input_map[2][1]  # Platform → cam 1
        _rp.RightPanel.set_atem_input_names(stub, {2: "New Name"})
        _, cam_key = stub._atem_input_map[2]
        assert cam_key == original_cam_key

    def test_unknown_input_gets_cam_key_zero(self):
        stub = _rp_stub()
        _rp.RightPanel.set_atem_input_names(stub, {9: "Aux Feed"})
        _, cam_key = stub._atem_input_map[9]
        assert cam_key == 0

    def test_resets_to_defaults_before_applying(self):
        """Re-calling with different names must not leave stale entries."""
        stub = _rp_stub()
        # First call adds input 9
        _rp.RightPanel.set_atem_input_names(stub, {9: "Stale"})
        assert 9 in stub._atem_input_map
        # Second call without input 9 should wipe it
        _rp.RightPanel.set_atem_input_names(stub, {1: "PC Live"})
        assert 9 not in stub._atem_input_map

    def test_empty_names_dict_resets_to_defaults(self):
        stub = _rp_stub()
        _rp.RightPanel.set_atem_input_names(stub, {2: "Changed"})
        _rp.RightPanel.set_atem_input_names(stub, {})
        label, _ = stub._atem_input_map[2]
        assert label == "Platform"  # back to default

    def test_multiple_inputs_updated_at_once(self):
        stub = _rp_stub()
        _rp.RightPanel.set_atem_input_names(stub, {1: "Desktop PC", 2: "Platform Cam", 3: "Comments Desk"})
        assert stub._atem_input_map[1][0] == "Desktop PC"
        assert stub._atem_input_map[2][0] == "Platform Cam"
        assert stub._atem_input_map[3][0] == "Comments Desk"

    def test_label_visible_in_on_air_after_name_update(self):
        stub = _rp_stub(_atem_has_program=True)
        _rp.RightPanel.set_atem_input_names(stub, {2: "Platform Camera HD"})
        _rp.RightPanel.set_atem_program(stub, 2)
        text = stub._on_air_label.setText.call_args[0][0]
        assert "Platform Camera HD" in text


# ══════════════════════════════════════════════════════════════════════════════
#  _update_mode_buttons
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateModeButtons:
    """_update_mode_buttons shows/hides buttons based on the current role."""

    def _stub_with_role(self, role):
        stub = _rp_stub()
        stub._mw._access_mode_svc.mode = role
        return stub

    def test_technician_shows_gear_btn(self):
        from domain.call_set_policy import OperatingMode
        stub = self._stub_with_role(OperatingMode.TECHNICIAN)
        _rp.RightPanel._update_mode_buttons(stub)
        stub._btn_gear.setVisible.assert_called_with(True)

    def test_technician_shows_exit_admin_btn(self):
        from domain.call_set_policy import OperatingMode
        stub = self._stub_with_role(OperatingMode.TECHNICIAN)
        _rp.RightPanel._update_mode_buttons(stub)
        stub._btn_exit_admin.setVisible.assert_called_with(True)

    def test_technician_hides_enter_admin_btn(self):
        from domain.call_set_policy import OperatingMode
        stub = self._stub_with_role(OperatingMode.TECHNICIAN)
        _rp.RightPanel._update_mode_buttons(stub)
        stub._btn_enter_admin.setVisible.assert_called_with(False)

    def test_system_admin_shows_settings_buttons(self):
        from domain.call_set_policy import OperatingMode
        stub = self._stub_with_role(OperatingMode.SYSTEM_ADMIN)
        _rp.RightPanel._update_mode_buttons(stub)
        stub._btn_gear.setVisible.assert_called_with(True)
        stub._btn_exit_admin.setVisible.assert_called_with(True)
        stub._btn_enter_admin.setVisible.assert_called_with(False)

    def test_camera_operator_hides_settings_shows_enter_admin(self):
        from domain.call_set_policy import OperatingMode
        stub = self._stub_with_role(OperatingMode.CAMERA_OPERATOR)
        _rp.RightPanel._update_mode_buttons(stub)
        stub._btn_gear.setVisible.assert_called_with(False)
        stub._btn_exit_admin.setVisible.assert_called_with(False)
        stub._btn_enter_admin.setVisible.assert_called_with(True)

    def test_basic_operator_hides_settings_shows_enter_admin(self):
        from domain.call_set_policy import OperatingMode
        stub = self._stub_with_role(OperatingMode.BASIC_OPERATOR)
        _rp.RightPanel._update_mode_buttons(stub)
        stub._btn_gear.setVisible.assert_called_with(False)
        stub._btn_enter_admin.setVisible.assert_called_with(True)


# ══════════════════════════════════════════════════════════════════════════════
#  _flash_button
# ══════════════════════════════════════════════════════════════════════════════

class TestFlashButton:
    """_flash_button sets green on success, red on failure."""

    def test_success_sets_green_color(self):
        stub = _rp_stub()
        stub._btn_focus_base_style = _BASE_STYLE
        btn = MagicMock()
        _rp.RightPanel._flash_button(stub, btn, success=True)
        style = btn.setStyleSheet.call_args[0][0]
        assert "#3d9e3d" in style

    def test_failure_sets_red_color(self):
        stub = _rp_stub()
        stub._btn_focus_base_style = _BASE_STYLE
        btn = MagicMock()
        _rp.RightPanel._flash_button(stub, btn, success=False)
        style = btn.setStyleSheet.call_args[0][0]
        assert "#b33030" in style

    def test_flash_calls_set_stylesheet_once(self):
        stub = _rp_stub()
        stub._btn_focus_base_style = _BASE_STYLE
        btn = MagicMock()
        _rp.RightPanel._flash_button(stub, btn, success=True)
        btn.setStyleSheet.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  set_pip_state
# ══════════════════════════════════════════════════════════════════════════════

class TestSetPipState:
    """set_pip_state shows/hides the PiP indicator and formats the source label."""

    def _pip(self, enabled, source=None):
        from types import SimpleNamespace
        return SimpleNamespace(enabled=enabled, source=source)

    def test_hides_label_when_pip_disabled(self):
        stub = _rp_stub()
        _rp.RightPanel.set_pip_state(stub, self._pip(False))
        stub._pip_label.hide.assert_called_once()
        stub._pip_label.show.assert_not_called()

    def test_hides_label_when_pip_state_is_none(self):
        stub = _rp_stub()
        _rp.RightPanel.set_pip_state(stub, None)
        stub._pip_label.hide.assert_called_once()

    def test_shows_label_when_pip_enabled(self):
        stub = _rp_stub()
        _rp.RightPanel.set_pip_state(stub, self._pip(True))
        stub._pip_label.show.assert_called_once()

    def test_label_text_without_source(self):
        stub = _rp_stub()
        _rp.RightPanel.set_pip_state(stub, self._pip(True, source=None))
        text = stub._pip_label.setText.call_args[0][0]
        assert "PiP ON" in text
        assert "src" not in text

    def test_label_text_with_source(self):
        stub = _rp_stub()
        _rp.RightPanel.set_pip_state(stub, self._pip(True, source=3))
        text = stub._pip_label.setText.call_args[0][0]
        assert "PiP ON" in text
        assert "3" in text

    def test_enabled_then_disabled_hides_label(self):
        stub = _rp_stub()
        _rp.RightPanel.set_pip_state(stub, self._pip(True))
        stub._pip_label.reset_mock()
        _rp.RightPanel.set_pip_state(stub, self._pip(False))
        stub._pip_label.hide.assert_called_once()
        stub._pip_label.show.assert_not_called()

