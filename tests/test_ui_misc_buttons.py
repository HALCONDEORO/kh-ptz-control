#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_ui_misc_buttons.py — Unit tests for remaining UI logic not covered elsewhere.

Covers:
  - ui/splash_screen.py  : TestResult, BootStatistics  (pure Python — no Qt needed)
  - ui/schedule_dialog.py: _toggle_always, _refresh_always_ui
  - ui/config_dialog.py  : _CamEditDialog._apply, _ATEMEditDialog._apply
  - ui/widgets.py        : GoButton / SpecialDragButton state and name logic
"""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ══════════════════════════════════════════════════════════════════════════════
#  PART 1 — TestResult and BootStatistics (pure Python, no Qt)
# ══════════════════════════════════════════════════════════════════════════════

# Minimal stubs so splash_screen.py can be imported without a real QApplication
# or real network hardware.  All Qt and hardware symbols are MagicMock'd.

def _ensure_all_qt_stubs() -> None:
    """Single comprehensive stub setup covering all Qt symbols used by every
    module imported in this test file."""
    # ── Create stub modules if real PyQt5 is not installed ───────────────────
    for mod in ("PyQt5", "PyQt5.QtCore", "PyQt5.QtWidgets", "PyQt5.QtGui", "PyQt5.QtSvg"):
        if mod not in sys.modules:
            sys.modules[mod] = types.ModuleType(mod)

    # ── QtCore ───────────────────────────────────────────────────────────────
    qtc = sys.modules["PyQt5.QtCore"]
    for attr in ("Qt", "pyqtSignal", "QTimer", "QRect", "QSize", "QObject",
                 "QPoint", "QMimeData", "QTime", "QByteArray", "QRectF"):
        if not hasattr(qtc, attr):
            setattr(qtc, attr, MagicMock())
    if not hasattr(sys.modules["PyQt5"], "QtCore"):
        sys.modules["PyQt5"].QtCore = qtc  # type: ignore[attr-defined]

    # ── QtWidgets ─────────────────────────────────────────────────────────────
    qtw = sys.modules["PyQt5.QtWidgets"]
    for attr in (
        "QWidget", "QVBoxLayout", "QHBoxLayout", "QLabel", "QProgressBar",
        "QFrame", "QSizePolicy", "QGraphicsDropShadowEffect", "QGraphicsOpacityEffect",
        "QDialog", "QCheckBox", "QTimeEdit", "QMessageBox", "QPushButton",
        "QLineEdit", "QComboBox", "QTabWidget", "QScrollArea", "QButtonGroup",
        "QRadioButton", "QApplication", "QToolButton", "QMenu", "QAction",
        "QAbstractItemView", "QListWidget", "QListWidgetItem", "QSlider",
        "QInputDialog",
    ):
        if not hasattr(qtw, attr):
            setattr(qtw, attr, MagicMock)
    # Ensure QMessageBox.Yes/No are integers for comparison
    qmb = qtw.QMessageBox
    if not hasattr(qmb, "Yes"):
        qmb.Yes = 16384
        qmb.No  = 65536

    # ── QtGui ─────────────────────────────────────────────────────────────────
    qtg = sys.modules["PyQt5.QtGui"]
    for attr in ("QColor", "QPainter", "QRadialGradient", "QPen",
                 "QBrush", "QLinearGradient", "QIcon", "QPixmap",
                 "QPainterPath", "QDrag"):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock)
    # QFont needs class-level constants (Bold, Normal) used at class-body time
    if not hasattr(qtg, "QFont"):
        class _FakeQFont:
            Bold = 75
            Normal = 50
            Black = 87
            def __init__(self, *a, **kw): pass
        qtg.QFont = _FakeQFont  # type: ignore[attr-defined]
    else:
        _qf = qtg.QFont
        if not hasattr(_qf, "Bold"):
            _qf.Bold = 75
        if not hasattr(_qf, "Normal"):
            _qf.Normal = 50
    if not hasattr(sys.modules["PyQt5"], "QtGui"):
        sys.modules["PyQt5"].QtGui = qtg  # type: ignore[attr-defined]

    # ── QtSvg ─────────────────────────────────────────────────────────────────
    qtsvg = sys.modules["PyQt5.QtSvg"]
    for attr in ("QSvgWidget", "QSvgRenderer"):
        if not hasattr(qtsvg, attr):
            setattr(qtsvg, attr, MagicMock)

    # ── External modules needed by splash_screen / config_dialog ─────────────
    if "application.camera_discovery" not in sys.modules:
        m = types.ModuleType("application.camera_discovery")
        m.get_camera_subnet = MagicMock(return_value="192.168.1.0/24")  # type: ignore[attr-defined]
        m.tcp_scan = MagicMock(return_value=[])  # type: ignore[attr-defined]
        m.arp_scan  = MagicMock(return_value=[])  # type: ignore[attr-defined]
        sys.modules["application.camera_discovery"] = m

    if "adapters.sim_mode" not in sys.modules:
        sm = types.ModuleType("adapters.sim_mode")
        sm.is_simulation = MagicMock(return_value=False)  # type: ignore[attr-defined]
        sys.modules["adapters.sim_mode"] = sm

    # ── ui.widgets stub (needed by config_dialog → ScheduleDialog) ────────────
    if "ui.widgets" not in sys.modules:
        class _FakeSDB:
            def __init__(self, *a, **kw):
                self.assigned_name = ""
                self._call_mode = False
                self.styleSheet = lambda: ""
                self.setStyleSheet = lambda s: None
            def set_name(self, name, emit_signal=True): self.assigned_name = name
            def _apply_style(self): pass

        _wm = types.ModuleType("ui.widgets")
        _wm.SpecialDragButton = _FakeSDB        # type: ignore[attr-defined]
        _wm.GoButton          = MagicMock       # type: ignore[attr-defined]
        _wm.DragDropButton    = MagicMock       # type: ignore[attr-defined]
        _wm.PresetActionMixin = MagicMock       # type: ignore[attr-defined]
        sys.modules["ui.widgets"] = _wm
    else:
        _wm = sys.modules["ui.widgets"]
        if not hasattr(_wm, "DragDropButton"):
            _wm.DragDropButton = MagicMock      # type: ignore[attr-defined]


_ensure_all_qt_stubs()

# Import only the pure-Python classes from splash_screen — not the whole module,
# which would fire RuntimePathResolver at import time.  We cherry-pick them.
from ui.splash_screen import TestResult, BootStatistics  # noqa: E402


class TestTestResult:
    """TestResult tracks name, success, timing and serialises to dict."""

    def test_initial_success_is_false(self):
        tr = TestResult("camera_ping")
        assert tr.success is False

    def test_initial_error_msg_is_none(self):
        tr = TestResult("camera_ping")
        assert tr.error_msg is None

    def test_finish_sets_success_true(self):
        tr = TestResult("camera_ping")
        tr.finish(True)
        assert tr.success is True

    def test_finish_sets_success_false(self):
        tr = TestResult("camera_ping")
        tr.finish(False)
        assert tr.success is False

    def test_finish_sets_error_message(self):
        tr = TestResult("camera_ping")
        tr.finish(False, error="timeout")
        assert tr.error_msg == "timeout"

    def test_finish_sets_duration_ms_non_negative(self):
        tr = TestResult("camera_ping")
        tr.finish(True)
        assert tr.duration_ms >= 0

    def test_to_dict_contains_name(self):
        tr = TestResult("camera_ping")
        tr.finish(True)
        assert tr.to_dict()["name"] == "camera_ping"

    def test_to_dict_contains_success(self):
        tr = TestResult("camera_ping")
        tr.finish(False)
        assert tr.to_dict()["success"] is False

    def test_to_dict_contains_duration_ms(self):
        tr = TestResult("camera_ping")
        tr.finish(True)
        assert "duration_ms" in tr.to_dict()

    def test_to_dict_contains_error_field(self):
        tr = TestResult("camera_ping")
        tr.finish(False, error="refused")
        d = tr.to_dict()
        assert d["error"] == "refused"

    def test_to_dict_contains_timestamp(self):
        tr = TestResult("camera_ping")
        tr.finish(True)
        assert "timestamp" in tr.to_dict()

    def test_to_dict_is_dict(self):
        tr = TestResult("x")
        tr.finish(True)
        assert isinstance(tr.to_dict(), dict)


class TestBootStatistics:
    """BootStatistics.get_summary() aggregates boot history from JSON file."""

    def _make_stats(self, tmp_path, entries: list) -> BootStatistics:
        f = tmp_path / "boot_stats.json"
        f.write_text(json.dumps(entries), encoding="utf-8")
        return BootStatistics(stats_file=str(f))

    def test_get_summary_empty_file_returns_empty_dict(self, tmp_path):
        bs = self._make_stats(tmp_path, [])
        assert bs.get_summary() == {}

    def test_get_summary_counts_total_boots(self, tmp_path):
        entries = [
            {"success": True, "duration_ms": 1000},
            {"success": False, "duration_ms": 2000},
        ]
        bs = self._make_stats(tmp_path, entries)
        assert bs.get_summary()["total_boots"] == 2

    def test_get_summary_counts_successful_boots(self, tmp_path):
        entries = [
            {"success": True, "duration_ms": 500},
            {"success": True, "duration_ms": 600},
            {"success": False, "duration_ms": 400},
        ]
        bs = self._make_stats(tmp_path, entries)
        assert bs.get_summary()["successful"] == 2

    def test_get_summary_calculates_average_duration(self, tmp_path):
        entries = [
            {"success": True, "duration_ms": 1000},
            {"success": True, "duration_ms": 3000},
        ]
        bs = self._make_stats(tmp_path, entries)
        assert bs.get_summary()["avg_duration_ms"] == 2000

    def test_get_summary_success_rate_100_percent(self, tmp_path):
        entries = [{"success": True, "duration_ms": 500}]
        bs = self._make_stats(tmp_path, entries)
        assert bs.get_summary()["success_rate"] == "100.0%"

    def test_get_summary_success_rate_zero_percent(self, tmp_path):
        entries = [{"success": False, "duration_ms": 500}]
        bs = self._make_stats(tmp_path, entries)
        assert bs.get_summary()["success_rate"] == "0.0%"

    def test_get_summary_includes_last_boot_timestamp(self, tmp_path):
        entries = [
            {"success": True, "duration_ms": 500, "timestamp": "2026-01-01T10:00:00"},
            {"success": True, "duration_ms": 600, "timestamp": "2026-01-02T11:00:00"},
        ]
        bs = self._make_stats(tmp_path, entries)
        assert bs.get_summary()["last_boot"] == "2026-01-02T11:00:00"

    def test_read_stats_handles_corrupt_json(self, tmp_path):
        f = tmp_path / "boot_stats.json"
        f.write_text("NOT JSON", encoding="utf-8")
        bs = BootStatistics(stats_file=str(f))
        assert bs._read_stats() == []

    def test_read_stats_handles_missing_file(self, tmp_path):
        bs = BootStatistics(stats_file=str(tmp_path / "nonexistent.json"))
        assert bs._read_stats() == []

    def test_read_stats_returns_list(self, tmp_path):
        entries = [{"success": True, "duration_ms": 500}]
        bs = self._make_stats(tmp_path, entries)
        result = bs._read_stats()
        assert isinstance(result, list)
        assert len(result) == 1


# ══════════════════════════════════════════════════════════════════════════════
#  PART 2 — ScheduleDialog._toggle_always / _refresh_always_ui
# ══════════════════════════════════════════════════════════════════════════════

# Qt stubs are already set up; schedule_dialog is tested via the existing
# test_schedule_dialog.py (which stubs separately).  We import via the same
# pattern — checking if already in sys.modules first.

import ui.schedule_dialog as _sd  # noqa: E402


def _schedule_stub(always_bypass: bool = False) -> MagicMock:
    stub = MagicMock()
    stub._always_bypass = always_bypass
    stub._day_rows_widgets = []   # no real rows — avoids iteration side-effects
    stub._time_style = MagicMock(return_value="")
    return stub


class TestToggleAlwaysBtn:
    """ON/OFF toggle button → _toggle_always flips _always_bypass."""

    def test_toggle_false_to_true(self):
        stub = _schedule_stub(always_bypass=False)
        _sd.ScheduleDialog._toggle_always(stub)
        assert stub._always_bypass is True

    def test_toggle_true_to_false(self):
        stub = _schedule_stub(always_bypass=True)
        _sd.ScheduleDialog._toggle_always(stub)
        assert stub._always_bypass is False

    def test_toggle_calls_refresh_ui(self):
        stub = _schedule_stub(always_bypass=False)
        _sd.ScheduleDialog._toggle_always(stub)
        stub._refresh_always_ui.assert_called_once()

    def test_double_toggle_restores_original_state(self):
        stub = _schedule_stub(always_bypass=False)
        _sd.ScheduleDialog._toggle_always(stub)
        _sd.ScheduleDialog._toggle_always(stub)
        assert stub._always_bypass is False


class TestRefreshAlwaysUI:
    """_refresh_always_ui sets button text ON/OFF and disables/enables rows."""

    def test_on_sets_btn_text_on(self):
        stub = _schedule_stub(always_bypass=True)
        _sd.ScheduleDialog._refresh_always_ui(stub)
        stub._btn_always.setText.assert_called_with("ON")

    def test_off_sets_btn_text_off(self):
        stub = _schedule_stub(always_bypass=False)
        _sd.ScheduleDialog._refresh_always_ui(stub)
        stub._btn_always.setText.assert_called_with("OFF")

    def test_on_sets_green_stylesheet_on_btn(self):
        stub = _schedule_stub(always_bypass=True)
        _sd.ScheduleDialog._refresh_always_ui(stub)
        style = stub._btn_always.setStyleSheet.call_args[0][0]
        assert "#4A7A44" in style or "green" in style.lower() or "4A7A" in style

    def test_off_sets_grey_stylesheet_on_btn(self):
        stub = _schedule_stub(always_bypass=False)
        _sd.ScheduleDialog._refresh_always_ui(stub)
        style = stub._btn_always.setStyleSheet.call_args[0][0]
        assert "#9e9e9e" in style or "grey" in style.lower() or "9e9e" in style

    def test_on_disables_rows(self):
        stub = _schedule_stub(always_bypass=True)
        chk, t_start, t_end = MagicMock(), MagicMock(), MagicMock()
        chk.isChecked.return_value = True
        stub._day_rows_widgets = [(chk, t_start, t_end)]
        _sd.ScheduleDialog._refresh_always_ui(stub)
        chk.setEnabled.assert_called_with(False)

    def test_off_enables_rows(self):
        stub = _schedule_stub(always_bypass=False)
        chk, t_start, t_end = MagicMock(), MagicMock(), MagicMock()
        chk.isChecked.return_value = True
        stub._day_rows_widgets = [(chk, t_start, t_end)]
        _sd.ScheduleDialog._refresh_always_ui(stub)
        chk.setEnabled.assert_called_with(True)


# ══════════════════════════════════════════════════════════════════════════════
#  PART 3 — _CamEditDialog._apply and _ATEMEditDialog._apply
# ══════════════════════════════════════════════════════════════════════════════

import ui.config_dialog as _cd  # noqa: E402


def _cam_stub(text: str, valid: bool, config_type: str = "ip", cam_num: int = 1) -> MagicMock:
    stub = MagicMock()
    stub._input.text.return_value = text
    stub._validate.return_value = valid
    stub._config_type = config_type
    stub._cam_num = cam_num
    stub._mw = MagicMock()
    return stub


class TestCamEditDialogApply:
    """_CamEditDialog._apply: validates input and updates camera config."""

    def test_empty_text_shows_error_and_does_not_accept(self):
        stub = _cam_stub(text="", valid=True)
        _cd._CamEditDialog._apply(stub)
        stub._err.setText.assert_called_once()
        stub.accept.assert_not_called()

    def test_whitespace_only_shows_error(self):
        stub = _cam_stub(text="   ", valid=True)
        _cd._CamEditDialog._apply(stub)
        stub._err.setText.assert_called_once()
        stub.accept.assert_not_called()

    def test_invalid_value_shows_format_error(self):
        stub = _cam_stub(text="not-an-ip", valid=False)
        _cd._CamEditDialog._apply(stub)
        stub._err.setText.assert_called_once()
        error_text = stub._err.setText.call_args[0][0]
        assert "Invalid" in error_text or "Expected" in error_text
        stub.accept.assert_not_called()

    def test_valid_ip_cam1_accepts(self):
        stub = _cam_stub(text="192.168.1.100", valid=True, config_type="ip", cam_num=1)
        with patch("ui.config_edit_dialogs._config_yaml_path", return_value=None), \
             patch("config.CAM1") as mc:
            mc.ip = "192.168.1.1"
            _cd._CamEditDialog._apply(stub)
        stub.accept.assert_called_once()

    def test_valid_ip_cam1_updates_config(self):
        # Since #893 the dialog delegates the write to CameraConfigService rather
        # than mutating config.CAM1 directly; assert the delegation.
        stub = _cam_stub(text="10.0.0.5", valid=True, config_type="ip", cam_num=1)
        _cd._CamEditDialog._apply(stub)
        stub._mw._camera_config.set_camera_ip.assert_called_once_with(1, "10.0.0.5")

    def test_valid_ip_cam2_updates_cam2_config(self):
        stub = _cam_stub(text="10.0.0.6", valid=True, config_type="ip", cam_num=2)
        _cd._CamEditDialog._apply(stub)
        stub._mw._camera_config.set_camera_ip.assert_called_once_with(2, "10.0.0.6")

    def test_valid_visca_id_cam1_updates_cam_id(self):
        stub = _cam_stub(text="1", valid=True, config_type="visca_id", cam_num=1)
        _cd._CamEditDialog._apply(stub)
        stub._mw._camera_config.set_camera_visca_id.assert_called_once_with(1, "1")

    def test_valid_visca_id_cam2_updates_cam2_id(self):
        stub = _cam_stub(text="2", valid=True, config_type="visca_id", cam_num=2)
        _cd._CamEditDialog._apply(stub)
        stub._mw._camera_config.set_camera_visca_id.assert_called_once_with(2, "2")

    def test_no_cameras_manager_still_accepts(self):
        stub = _cam_stub(text="192.168.1.50", valid=True, config_type="ip", cam_num=1)
        stub._mw = None
        with patch("ui.config_edit_dialogs._config_yaml_path", return_value=None), \
             patch("config.CAM1") as mc:
            mc.ip = "192.168.1.1"
            _cd._CamEditDialog._apply(stub)
        stub.accept.assert_called_once()


class TestAtemEditDialogApply:
    """_ATEMEditDialog._apply: validates IP and updates ATEM config."""

    def _atem_stub(self, text: str) -> MagicMock:
        stub = MagicMock()
        stub._input.text.return_value = text
        return stub

    def test_empty_text_shows_error_and_does_not_accept(self):
        stub = self._atem_stub("")
        _cd._ATEMEditDialog._apply(stub)
        stub._err.setText.assert_called_once()
        stub.accept.assert_not_called()

    def test_invalid_ip_shows_error(self):
        stub = self._atem_stub("not-an-ip")
        with patch("ui.config_edit_dialogs.is_valid_ip", return_value=False):
            _cd._ATEMEditDialog._apply(stub)
        stub._err.setText.assert_called_once()
        stub.accept.assert_not_called()

    def test_valid_ip_updates_atem_config(self):
        # Since #893 the dialog delegates the write to CameraConfigService.
        stub = self._atem_stub("10.0.0.1")
        with patch("ui.config_edit_dialogs.is_valid_ip", return_value=True):
            _cd._ATEMEditDialog._apply(stub)
        stub._mw._camera_config.set_atem_ip.assert_called_once_with("10.0.0.1")

    def test_valid_ip_accepts(self):
        stub = self._atem_stub("10.0.0.1")
        with patch("ui.config_edit_dialogs.is_valid_ip", return_value=True):
            _cd._ATEMEditDialog._apply(stub)
        stub.accept.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  PART 4 — GoButton / SpecialDragButton state and name logic
# ══════════════════════════════════════════════════════════════════════════════


# ── Load REAL GoButton/SpecialDragButton via importlib (bypasses sys.modules) ─
import importlib.util as _ilu
import pathlib as _pl

_WIDGETS_SRC = _pl.Path(__file__).parent.parent / 'ui' / 'widgets.py'
_spec_w = _ilu.spec_from_file_location('_widgets_impl_', _WIDGETS_SRC)
_wmod = _ilu.module_from_spec(_spec_w)  # type: ignore[arg-type]
try:
    _spec_w.loader.exec_module(_wmod)   # type: ignore[union-attr]
    _GoButton          = _wmod.GoButton
    _SpecialDragButton = _wmod.SpecialDragButton
    _WIDGETS_LOADED    = True
except Exception:
    _GoButton = _SpecialDragButton = None
    _WIDGETS_LOADED = False

_need_widgets = pytest.mark.skipif(
    not _WIDGETS_LOADED,
    reason='ui/widgets.py could not be loaded with Qt stubs',
)



# ── GoButton helpers ──────────────────────────────────────────────────────────

def _go_stub(seat_number: int = 5, assigned_name: str = "") -> MagicMock:
    stub = MagicMock()
    stub.seat_number = seat_number
    stub.assigned_name = assigned_name
    stub._preset_state = None
    stub._preset_pending = False
    stub._feedback_timer = None
    return stub


@_need_widgets
class TestGoButtonSetName:
    """GoButton.set_name sets assigned_name and button label correctly."""

    def test_set_name_updates_assigned_name(self):
        stub = _go_stub()
        _GoButton.set_name(stub, "PersonA Smith")
        assert stub.assigned_name == "PersonA Smith"

    def test_set_name_shows_first_word_only(self):
        stub = _go_stub()
        _GoButton.set_name(stub, "PersonA Smith")
        stub.setText.assert_called_with("PersonA")

    def test_set_name_empty_shows_seat_number(self):
        stub = _go_stub(seat_number=7)
        _GoButton.set_name(stub, "")
        stub.setText.assert_called_with("7")

    def test_set_name_calls_apply_style(self):
        stub = _go_stub()
        _GoButton.set_name(stub, "PersonB")
        stub._apply_style.assert_called_once()

    def test_set_name_emits_signal_by_default(self):
        stub = _go_stub(seat_number=3)
        _GoButton.set_name(stub, "PersonC")
        stub.name_assigned.emit.assert_called_once_with(3, "PersonC")

    def test_set_name_no_emit_when_false(self):
        stub = _go_stub()
        _GoButton.set_name(stub, "Dave", emit_signal=False)
        stub.name_assigned.emit.assert_not_called()

    def test_set_name_single_word_name(self):
        stub = _go_stub()
        _GoButton.set_name(stub, "Eve")
        stub.setText.assert_called_with("Eve")


@_need_widgets
class TestGoButtonPresetState:
    """GoButton preset state machine: show_saving, show_saved, _reset."""

    def test_reset_preset_state_clears_state(self):
        stub = _go_stub()
        stub._preset_state = "saving"
        _GoButton._reset_preset_state(stub)
        assert stub._preset_state is None

    def test_show_test_result_warning_sets_state(self):
        stub = _go_stub()
        stub._feedback_timer = None
        orig_qt = getattr(_wmod, "QTimer", None)
        try:
            if orig_qt is not None:
                _wmod.QTimer = MagicMock()
            _GoButton.show_test_result(stub, "warning")
        finally:
            if orig_qt is not None:
                _wmod.QTimer = orig_qt
        assert stub._preset_state == "test_warning"

    def test_show_test_result_error_sets_state(self):
        stub = _go_stub()
        stub._feedback_timer = None
        orig_qt = getattr(_wmod, "QTimer", None)
        try:
            if orig_qt is not None:
                _wmod.QTimer = MagicMock()
            _GoButton.show_test_result(stub, "error")
        finally:
            if orig_qt is not None:
                _wmod.QTimer = orig_qt
        assert stub._preset_state == "test_error"

    def test_show_test_result_active_calls_activate(self):
        stub = _go_stub()
        _GoButton.show_test_result(stub, "active")
        stub.activate.assert_called_once()

    def test_show_test_result_ok_calls_show_saved(self):
        stub = _go_stub()
        _GoButton.show_test_result(stub, "ok")
        stub.show_saved.assert_called_once()

    def test_show_test_result_unknown_calls_deactivate_and_reset(self):
        stub = _go_stub()
        _GoButton.show_test_result(stub, "clear")
        stub._deactivate.assert_called_once()
        stub._reset_preset_state.assert_called_once()

    def test_set_preset_pending_sets_flag(self):
        stub = _go_stub()
        _GoButton.set_preset_pending(stub, True)
        assert stub._preset_pending is True

    def test_set_preset_pending_false_clears_flag(self):
        stub = _go_stub()
        stub._preset_pending = True
        _GoButton.set_preset_pending(stub, False)
        assert stub._preset_pending is False

    def test_set_preset_pending_calls_update(self):
        stub = _go_stub()
        _GoButton.set_preset_pending(stub, True)
        stub.update.assert_called_once()


@pytest.fixture(autouse=False)
def _pulse_state():
    """Save and restore GoButton class-level pulse state around each test."""
    if not _WIDGETS_LOADED:
        yield
        return
    saved = (_GoButton._pulse_phase, _GoButton._pulse_cycles, _GoButton._active_button)
    yield
    _GoButton._pulse_phase, _GoButton._pulse_cycles, _GoButton._active_button = saved


@_need_widgets
class TestGoButtonAdvancePulse:
    """GoButton._advance_pulse class-level phase accumulator."""

    @pytest.fixture(autouse=True)
    def _restore_pulse(self, _pulse_state):
        """Automatically restore GoButton pulse state after every test."""
        pass  # the module-level fixture handles save/restore

    def test_advance_increments_phase(self):
        _GoButton._pulse_phase = 0.0
        _GoButton._pulse_cycles = 0
        _GoButton._active_button = None
        _GoButton._advance_pulse()
        assert _GoButton._pulse_phase > 0.0

    def test_phase_wraps_at_one(self):
        _GoButton._pulse_phase = 0.99
        _GoButton._pulse_cycles = 0
        _GoButton._active_button = None
        _GoButton._advance_pulse()
        assert _GoButton._pulse_phase < 0.1   # wrapped

    def test_phase_exceeding_1_increments_cycles(self):
        _GoButton._pulse_phase = 0.98
        _GoButton._pulse_cycles = 0
        _GoButton._active_button = None
        _GoButton._advance_pulse()
        assert _GoButton._pulse_cycles == 1

    def test_3_cycles_deactivates_active_button(self):
        mock_btn = MagicMock()
        _GoButton._pulse_phase = 0.98
        _GoButton._pulse_cycles = 2        # will become 3 on advance
        _GoButton._active_button = mock_btn
        _GoButton._advance_pulse()
        mock_btn._deactivate.assert_called_once()


@_need_widgets
class TestGoButtonClearConfirmMsg:
    """GoButton._clear_confirm_msg returns seat-specific message."""

    def test_includes_assigned_name(self):
        stub = _go_stub(seat_number=4, assigned_name="Frank")
        msg = _GoButton._clear_confirm_msg(stub)
        assert "Frank" in msg

    def test_includes_seat_number(self):
        stub = _go_stub(seat_number=4, assigned_name="Frank")
        msg = _GoButton._clear_confirm_msg(stub)
        assert "4" in msg


@_need_widgets
class TestSpecialDragButtonSetName:
    """SpecialDragButton.set_name uses default_label when name is empty."""

    def _sdb_stub(self, seat_id: int = 1, default_label: str = "Chairman",
                  assigned_name: str = "") -> MagicMock:
        stub = MagicMock()
        stub.seat_number = seat_id
        stub._default_label = default_label
        stub.assigned_name = assigned_name
        return stub

    def test_set_name_updates_assigned_name(self):
        stub = self._sdb_stub()
        _SpecialDragButton.set_name(stub, "PersonA Smith")
        assert stub.assigned_name == "PersonA Smith"

    def test_set_name_shows_first_word(self):
        stub = self._sdb_stub()
        _SpecialDragButton.set_name(stub, "PersonA Smith")
        stub.setText.assert_called_with("PersonA")

    def test_clear_name_shows_default_label(self):
        stub = self._sdb_stub(default_label="Chairman")
        _SpecialDragButton.set_name(stub, "")
        stub.setText.assert_called_with("Chairman")

    def test_set_name_emits_signal(self):
        stub = self._sdb_stub(seat_id=1)
        _SpecialDragButton.set_name(stub, "Grace")
        stub.name_assigned.emit.assert_called_once_with(1, "Grace")

    def test_set_name_no_emit_when_false(self):
        stub = self._sdb_stub()
        _SpecialDragButton.set_name(stub, "Grace", emit_signal=False)
        stub.name_assigned.emit.assert_not_called()

    def test_set_name_calls_apply_style(self):
        stub = self._sdb_stub()
        _SpecialDragButton.set_name(stub, "Grace")
        stub._apply_style.assert_called_once()

    def test_set_preset_pending_sets_flag(self):
        stub = self._sdb_stub()
        _SpecialDragButton.set_preset_pending(stub, True)
        assert stub._preset_pending is True

    def test_set_preset_pending_calls_update(self):
        stub = self._sdb_stub()
        _SpecialDragButton.set_preset_pending(stub, True)
        stub.update.assert_called_once()


@_need_widgets
class TestSpecialDragButtonClearConfirmMsg:
    """SpecialDragButton._clear_confirm_msg uses default_label."""

    def test_includes_assigned_name(self):
        stub = MagicMock()
        stub.assigned_name = "PersonA"
        stub._default_label = "Chairman"
        msg = _SpecialDragButton._clear_confirm_msg(stub)
        assert "PersonA" in msg

    def test_includes_default_label(self):
        stub = MagicMock()
        stub.assigned_name = "PersonA"
        stub._default_label = "Chairman"
        msg = _SpecialDragButton._clear_confirm_msg(stub)
        assert "Chairman" in msg
