#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_names_panel_buttons.py — Unit tests for NamesPanel button handlers.

Tests run headless: methods are called as unbound functions with a MagicMock
stub acting as self.  Qt modules are stubbed before import.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch



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
    if not hasattr(sys.modules["PyQt5"], "QtCore"):
        sys.modules["PyQt5"].QtCore = qtc  # type: ignore[attr-defined]

    qtw = sys.modules["PyQt5.QtWidgets"]
    for attr in (
        "QFrame", "QHBoxLayout", "QLabel", "QLineEdit", "QPushButton",
        "QVBoxLayout", "QWidget", "QScrollArea", "QSizePolicy",
        "QAbstractItemView", "QListWidget", "QListWidgetItem", "QButtonGroup",
        "QSlider", "QMessageBox", "QDialog", "QInputDialog", "QApplication",
        "QGraphicsDropShadowEffect",
    ):
        if not hasattr(qtw, attr):
            setattr(qtw, attr, MagicMock)

    # QMessageBox.Yes / QMessageBox.No need to be integers for comparison
    qmb = sys.modules["PyQt5.QtWidgets"].QMessageBox
    if not hasattr(qmb, "Yes"):
        qmb.Yes = 16384
        qmb.No = 65536

    # Also set QtCore/QtGui as PyQt5 submodule attrs (imported as `from PyQt5 import QtCore`)
    qtc = sys.modules["PyQt5.QtCore"]
    if not hasattr(sys.modules["PyQt5"], "QtCore"):
        sys.modules["PyQt5"].QtCore = qtc  # type: ignore[attr-defined]

    qtg = sys.modules["PyQt5.QtGui"]
    for attr in ("QColor", "QPainter", "QDrag", "QPixmap", "QIcon",
                 "QPen", "QPainterPath"):
        if not hasattr(qtg, attr):
            setattr(qtg, attr, MagicMock)
    if not hasattr(qtg, "QFont"):
        class _FakeQFont:
            Bold = 75
            Normal = 50
            def __init__(self, *args, **kwargs): pass
        qtg.QFont = _FakeQFont  # type: ignore[attr-defined]
    else:
        _qf = qtg.QFont
        if not hasattr(_qf, "Bold"):
            _qf.Bold = 75
    if not hasattr(sys.modules["PyQt5"], "QtGui"):
        sys.modules["PyQt5"].QtGui = qtg  # type: ignore[attr-defined]

    qtsvg = sys.modules["PyQt5.QtSvg"]
    for attr in ("QSvgWidget", "QSvgRenderer"):
        if not hasattr(qtsvg, attr):
            setattr(qtsvg, attr, MagicMock)


_ensure_qt_stubs()

# ui.widgets stub: names_panel needs DragDropButton (plus SpecialDragButton/GoButton)
if "ui.widgets" not in sys.modules:
    class _FakeSpecialDragButton:
        def __init__(self, seat_id=None, default_label=None, parent=None):
            self.seat_id = seat_id
            self.assigned_name = ""
            self._call_mode = False
            self.styleSheet = lambda: ""
            self.setStyleSheet = lambda s: None

        def set_name(self, name, emit_signal=True):
            self.assigned_name = name

        def _apply_style(self): pass

    _widgets_mod = types.ModuleType("ui.widgets")
    _widgets_mod.SpecialDragButton = _FakeSpecialDragButton  # type: ignore[attr-defined]
    _widgets_mod.GoButton = MagicMock                        # type: ignore[attr-defined]
    _widgets_mod.DragDropButton = MagicMock                  # type: ignore[attr-defined]
    _widgets_mod.PresetActionMixin = MagicMock               # type: ignore[attr-defined]
    sys.modules["ui.widgets"] = _widgets_mod
else:
    # Ensure DragDropButton exists in whatever stub is already there
    _wm = sys.modules["ui.widgets"]
    if not hasattr(_wm, "DragDropButton"):
        _wm.DragDropButton = MagicMock  # type: ignore[attr-defined]

import ui.names_panel as _np  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

def _panel_stub(names=None, assigned=None) -> MagicMock:
    """MagicMock acting as NamesPanel self."""
    stub = MagicMock()
    stub.names = list(names or [])
    stub._assigned = set(assigned or [])
    stub._on_changed = MagicMock()
    stub._rebuild = MagicMock()
    stub._clear_all_cb = MagicMock()
    return stub


# ══════════════════════════════════════════════════════════════════════════════
#  _add_name button
# ══════════════════════════════════════════════════════════════════════════════

class TestAddNameBtn:
    """＋ Add button → _add_name: validates input and appends to list."""

    def test_cancel_does_nothing(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("", False)):
            _np.NamesPanel._add_name(stub)
        assert stub.names == ["PersonA"]
        stub._on_changed.assert_not_called()

    def test_empty_text_does_nothing(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("   ", True)):
            _np.NamesPanel._add_name(stub)
        assert stub.names == ["PersonA"]
        stub._on_changed.assert_not_called()

    def test_duplicate_shows_messagebox_and_does_not_add(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("PersonA", True)), \
             patch("ui.names_panel.QMessageBox") as mock_mb:
            _np.NamesPanel._add_name(stub)
        mock_mb.information.assert_called_once()
        assert stub.names == ["PersonA"]
        stub._on_changed.assert_not_called()

    def test_valid_name_appended(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("PersonB", True)):
            _np.NamesPanel._add_name(stub)
        assert "PersonB" in stub.names

    def test_valid_name_triggers_on_changed(self):
        stub = _panel_stub(names=[])
        with patch("ui.names_panel._get_text", return_value=("PersonB", True)):
            _np.NamesPanel._add_name(stub)
        stub._on_changed.assert_called_once()

    def test_valid_name_triggers_rebuild(self):
        stub = _panel_stub(names=[])
        with patch("ui.names_panel._get_text", return_value=("PersonB", True)):
            _np.NamesPanel._add_name(stub)
        stub._rebuild.assert_called_once()

    def test_name_is_stripped_before_add(self):
        stub = _panel_stub(names=[])
        with patch("ui.names_panel._get_text", return_value=("  PersonB  ", True)):
            _np.NamesPanel._add_name(stub)
        assert "PersonB" in stub.names
        assert "  PersonB  " not in stub.names


# ══════════════════════════════════════════════════════════════════════════════
#  _delete_name_direct (🗑 inline button)
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteNameBtn:
    """Del button → _delete_name_direct: removes name after confirmation."""

    def _qmb_yes(self):
        return sys.modules["PyQt5.QtWidgets"].QMessageBox.Yes

    def _qmb_no(self):
        return sys.modules["PyQt5.QtWidgets"].QMessageBox.No

    def test_confirm_yes_removes_name(self):
        stub = _panel_stub(names=["PersonA", "PersonB"])
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_yes()
            _np.NamesPanel._delete_name_direct(stub, "PersonA")
        assert "PersonA" not in stub.names

    def test_confirm_yes_calls_on_changed(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_yes()
            _np.NamesPanel._delete_name_direct(stub, "PersonA")
        stub._on_changed.assert_called_once()

    def test_confirm_yes_triggers_rebuild(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_yes()
            _np.NamesPanel._delete_name_direct(stub, "PersonA")
        stub._rebuild.assert_called_once()

    def test_confirm_no_keeps_name(self):
        stub = _panel_stub(names=["PersonA", "PersonB"])
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_no()
            _np.NamesPanel._delete_name_direct(stub, "PersonA")
        assert "PersonA" in stub.names
        stub._on_changed.assert_not_called()

    def test_confirm_no_does_not_rebuild(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_no()
            _np.NamesPanel._delete_name_direct(stub, "PersonA")
        stub._rebuild.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
#  _edit_name_direct (✏ inline button)
# ══════════════════════════════════════════════════════════════════════════════

class TestEditNameBtn:
    """✏ Edit button → _edit_name_direct: renames with validation."""

    def test_cancel_is_noop(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("", False)):
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        assert stub.names == ["PersonA"]
        stub._on_changed.assert_not_called()

    def test_same_name_is_noop(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("PersonA", True)):
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        stub._on_changed.assert_not_called()
        stub._rebuild.assert_not_called()

    def test_duplicate_shows_messagebox_no_rename(self):
        stub = _panel_stub(names=["PersonA", "PersonB"])
        with patch("ui.names_panel._get_text", return_value=("PersonB", True)), \
             patch("ui.names_panel.QMessageBox") as mock_mb:
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        mock_mb.information.assert_called_once()
        assert "PersonA" in stub.names
        stub._on_changed.assert_not_called()

    def test_valid_rename_replaces_name(self):
        stub = _panel_stub(names=["PersonA", "PersonC"])
        with patch("ui.names_panel._get_text", return_value=("PersonB", True)):
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        assert "PersonB" in stub.names
        assert "PersonA" not in stub.names

    def test_valid_rename_calls_on_changed_with_old_and_new(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("PersonB", True)):
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        stub._on_changed.assert_called_once_with(old_name="PersonA", new_name="PersonB")

    def test_valid_rename_triggers_rebuild(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("PersonB", True)):
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        stub._rebuild.assert_called_once()

    def test_new_name_is_stripped(self):
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("  PersonB  ", True)):
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        assert "PersonB" in stub.names

    def test_whitespace_only_new_name_is_noop(self):
        """Input of only whitespace strips to empty string → noop (same as cancel)."""
        stub = _panel_stub(names=["PersonA"])
        with patch("ui.names_panel._get_text", return_value=("   ", True)):
            _np.NamesPanel._edit_name_direct(stub, "PersonA")
        assert stub.names == ["PersonA"]
        stub._on_changed.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
#  _clear_all button (🔄 Bring All Back)
# ══════════════════════════════════════════════════════════════════════════════

class TestClearAllBtn:
    """🔄 Bring All Back → _clear_all: confirms before delegating to callback."""

    def _qmb_yes(self):
        return sys.modules["PyQt5.QtWidgets"].QMessageBox.Yes

    def _qmb_no(self):
        return sys.modules["PyQt5.QtWidgets"].QMessageBox.No

    def test_no_assigned_returns_early(self):
        stub = _panel_stub(assigned=set())
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            _np.NamesPanel._clear_all(stub)
        mock_mb.question.assert_not_called()
        stub._clear_all_cb.assert_not_called()

    def test_with_assigned_shows_confirmation(self):
        stub = _panel_stub(assigned={"PersonA"})
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_no()
            _np.NamesPanel._clear_all(stub)
        mock_mb.question.assert_called_once()

    def test_yes_calls_clear_all_cb(self):
        stub = _panel_stub(assigned={"PersonA"})
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_yes()
            _np.NamesPanel._clear_all(stub)
        stub._clear_all_cb.assert_called_once()

    def test_no_does_not_call_clear_all_cb(self):
        stub = _panel_stub(assigned={"PersonA"})
        with patch("ui.names_panel.QMessageBox") as mock_mb:
            mock_mb.Yes = self._qmb_yes()
            mock_mb.No = self._qmb_no()
            mock_mb.question.return_value = self._qmb_no()
            _np.NamesPanel._clear_all(stub)
        stub._clear_all_cb.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
#  _on_order_changed (drag & drop reorder)
# ══════════════════════════════════════════════════════════════════════════════

class TestOnOrderChanged:
    """_on_order_changed reconstructs names list respecting assigned seats."""

    def _run(self, names, assigned, new_order):
        stub = _panel_stub(names=names, assigned=assigned)
        _np.NamesPanel._on_order_changed(stub, new_order)
        return stub

    def test_no_assigned_applies_new_order(self):
        stub = self._run(["PersonA", "PersonB", "PersonC"], set(), ["PersonC", "PersonB", "PersonA"])
        assert stub.names == ["PersonC", "PersonB", "PersonA"]

    def test_assigned_name_stays_in_place(self):
        # PersonB is assigned → doesn't appear in new_order; his position keeps PersonB
        stub = self._run(["PersonA", "PersonB", "PersonC"], {"PersonB"}, ["PersonC", "PersonA"])
        assert stub.names[1] == "PersonB"

    def test_unassigned_names_reordered_around_assigned(self):
        # Original: [PersonA(unassigned), PersonB(assigned), PersonC(unassigned)]
        # new_order: [PersonC, PersonA]
        stub = self._run(["PersonA", "PersonB", "PersonC"], {"PersonB"}, ["PersonC", "PersonA"])
        assert stub.names == ["PersonC", "PersonB", "PersonA"]

    def test_on_changed_called_after_reorder(self):
        stub = self._run(["PersonA", "PersonB"], set(), ["PersonB", "PersonA"])
        stub._on_changed.assert_called_once()

    def test_names_updated_in_place(self):
        names = ["PersonA", "PersonB"]
        stub = _panel_stub(names=names, assigned=set())
        original_list = stub.names  # same object reference
        _np.NamesPanel._on_order_changed(stub, ["PersonB", "PersonA"])
        # names[:] = ... updates in-place — same object, new contents
        assert original_list == ["PersonB", "PersonA"]
        assert stub.names is original_list  # must be the same list, not a replacement

    def test_all_assigned_new_order_is_empty_names_unchanged(self):
        stub = self._run(["PersonA", "PersonB"], {"PersonA", "PersonB"}, [])
        assert "PersonA" in stub.names
        assert "PersonB" in stub.names


# ══════════════════════════════════════════════════════════════════════════════
#  Search box (A1) + recall by name (B3)
# ══════════════════════════════════════════════════════════════════════════════

class TestSearchAndRecall:
    """Search filters the list (A1); Enter in Call mode recalls a seat (B3)."""

    def test_search_changed_sets_filter_and_rebuilds(self):
        stub = _panel_stub()
        _np.NamesPanel._on_search_changed(stub, "  bob ")
        assert stub._filter == "bob"
        stub._rebuild.assert_called_once()

    def test_enter_in_call_mode_recalls(self):
        stub = _panel_stub()
        stub._edit_mode = False
        stub._search.text.return_value = "PersonA"
        stub._recall_by_name_cb = MagicMock()
        _np.NamesPanel._on_search_enter(stub)
        stub._recall_by_name_cb.assert_called_once_with("PersonA")

    def test_enter_in_edit_mode_does_not_recall(self):
        stub = _panel_stub()
        stub._edit_mode = True
        stub._search.text.return_value = "PersonA"
        stub._recall_by_name_cb = MagicMock()
        _np.NamesPanel._on_search_enter(stub)
        stub._recall_by_name_cb.assert_not_called()

    def test_enter_with_blank_query_does_nothing(self):
        stub = _panel_stub()
        stub._edit_mode = False
        stub._search.text.return_value = "   "
        stub._recall_by_name_cb = MagicMock()
        _np.NamesPanel._on_search_enter(stub)
        stub._recall_by_name_cb.assert_not_called()

    def test_undo_delegates_to_callback(self):
        stub = _panel_stub()
        stub._undo_cb = MagicMock()
        _np.NamesPanel._undo(stub)
        stub._undo_cb.assert_called_once()

    def test_undo_noop_when_callback_missing(self):
        stub = _panel_stub()
        stub._undo_cb = None
        _np.NamesPanel._undo(stub)  # must not raise


# ══════════════════════════════════════════════════════════════════════════════
#  Title counter (A3)
# ══════════════════════════════════════════════════════════════════════════════

class TestTitleCounter:
    """_update_title shows seated/total counts."""

    def test_counter_reflects_assigned_and_total(self):
        stub = _panel_stub(names=["PersonA", "PersonB", "PersonC"], assigned={"PersonB"})
        _np.NamesPanel._update_title(stub)
        stub._title.setText.assert_called_once_with("👥 Attendees  (1/3 seated)")

    def test_counter_zero_seated(self):
        stub = _panel_stub(names=["PersonA"], assigned=set())
        _np.NamesPanel._update_title(stub)
        stub._title.setText.assert_called_once_with("👥 Attendees  (0/1 seated)")

