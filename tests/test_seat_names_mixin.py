#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_seat_names_mixin.py — Unit tests for SeatNamesController.

Methods are called as unbound functions with a MagicMock stub acting as self.
No Qt imports are needed — SeatNamesController is pure Python logic.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch


# ── Stub ui.widgets (SeatNamesController imports GoButton and SpecialDragButton) ─
if "ui.widgets" not in sys.modules:
    _wm = types.ModuleType("ui.widgets")
    _wm.GoButton = MagicMock          # type: ignore[attr-defined]
    _wm.SpecialDragButton = MagicMock  # type: ignore[attr-defined]
    sys.modules["ui.widgets"] = _wm

from ui.seat_names_mixin import SeatNamesController  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeSeat:
    """Minimal seat button double: records set_name calls."""
    def __init__(self, name: str = ""):
        self.assigned_name = name
        self._calls: list[tuple[str, bool]] = []

    def set_name(self, name: str, emit_signal: bool = True) -> None:
        self.assigned_name = name
        self._calls.append((name, emit_signal))


def _ctrl_stub(seats: dict | None = None, seat_names: dict | None = None,
               names_list: list | None = None) -> tuple[SeatNamesController, MagicMock]:
    """Return (controller, window_mock) with optional fake seats attached."""
    window = MagicMock()
    window._seat_names = dict(seat_names or {})
    window._names_list = list(names_list or [])

    # Attach fake seat buttons as Seat<key> attributes
    for key, seat in (seats or {}).items():
        setattr(window, f"Seat{key}", seat)

    ctrl = SeatNamesController(window)
    return ctrl, window


# ══════════════════════════════════════════════════════════════════════════════
#  _on_seat_name_assigned
# ══════════════════════════════════════════════════════════════════════════════

class TestOnSeatNameAssigned:
    """Assigning a name to a seat persists and syncs the panel."""

    def test_assigns_name_to_seat(self):
        ctrl, w = _ctrl_stub()
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "PersonA")
        assert w._seat_names["5"] == "PersonA"

    def test_empty_name_removes_key(self):
        ctrl, w = _ctrl_stub(seat_names={"5": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "")
        assert "5" not in w._seat_names

    def test_saves_names_data(self):
        ctrl, w = _ctrl_stub()
        with patch("ui.seat_names_mixin.save_names_data") as mock_save:
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "PersonA")
        mock_save.assert_called_once()

    def test_syncs_assigned_to_panel(self):
        ctrl, w = _ctrl_stub()
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "PersonA")
        w._names_panel.set_assigned.assert_called_once()

    def test_exclusivity_clears_other_seat_with_same_name(self):
        seat3 = _FakeSeat("PersonA")
        ctrl, w = _ctrl_stub(
            seats={"3": seat3},
            seat_names={"3": "PersonA"},
        )
        # Override isinstance so GoButton check passes for our fake
        with patch("ui.seat_names_mixin.save_names_data"), \
             patch("ui.seat_names_mixin.GoButton", _FakeSeat), \
             patch("ui.seat_names_mixin.SpecialDragButton", _FakeSeat):
            SeatNamesController._on_seat_name_assigned(ctrl, 7, "PersonA")
        # The old seat 3 must have been cleared
        assert w._seat_names.get("3") is None
        assert seat3.assigned_name == ""

    def test_exclusivity_does_not_clear_same_seat(self):
        seat5 = _FakeSeat("PersonA")
        ctrl, w = _ctrl_stub(
            seats={"5": seat5},
            seat_names={"5": "PersonA"},
        )
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "PersonA")
        # Re-assigning same name to same seat: no clearing
        assert seat5.assigned_name == "PersonA"


# ══════════════════════════════════════════════════════════════════════════════
#  _on_names_list_changed
# ══════════════════════════════════════════════════════════════════════════════

class TestOnNamesListChanged:
    """Renaming a person renames their seat assignment everywhere."""

    def test_renames_seat_name_entry(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_names_list_changed(
                ctrl, old_name="PersonA", new_name="Alicia"
            )
        assert w._seat_names["3"] == "Alicia"

    def test_renames_seat_button_label(self):
        seat3 = _FakeSeat("PersonA")
        ctrl, w = _ctrl_stub(seats={"3": seat3}, seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data"), \
             patch("ui.seat_names_mixin.GoButton", _FakeSeat), \
             patch("ui.seat_names_mixin.SpecialDragButton", _FakeSeat):
            SeatNamesController._on_names_list_changed(
                ctrl, old_name="PersonA", new_name="Alicia"
            )
        assert seat3.assigned_name == "Alicia"

    def test_seat_button_rename_uses_emit_false(self):
        seat3 = _FakeSeat("PersonA")
        ctrl, w = _ctrl_stub(seats={"3": seat3}, seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data"), \
             patch("ui.seat_names_mixin.GoButton", _FakeSeat), \
             patch("ui.seat_names_mixin.SpecialDragButton", _FakeSeat):
            SeatNamesController._on_names_list_changed(
                ctrl, old_name="PersonA", new_name="Alicia"
            )
        _, emit = seat3._calls[-1]
        assert emit is False

    def test_does_nothing_when_old_or_new_name_is_none(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data") as mock_save:
            SeatNamesController._on_names_list_changed(ctrl)  # no args
        # save_names_data should still be called (persistence)
        mock_save.assert_called_once()
        # Seat names should be unchanged
        assert w._seat_names["3"] == "PersonA"

    def test_renames_preset_service(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_names_list_changed(
                ctrl, old_name="PersonA", new_name="PersonB"
            )
        w._preset_svc.rename.assert_called_once_with("PersonA", "PersonB")

    def test_saves_names_data(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data") as mock_save:
            SeatNamesController._on_names_list_changed(
                ctrl, old_name="PersonA", new_name="PersonB"
            )
        mock_save.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
#  _clear_all_seats
# ══════════════════════════════════════════════════════════════════════════════

class TestClearAllSeats:
    """_clear_all_seats clears every seat button and saves empty state."""

    def test_clears_seat_names_dict(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA", "5": "PersonB"})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._clear_all_seats(ctrl)
        assert w._seat_names == {}

    def test_clears_seat_button_labels(self):
        seat3 = _FakeSeat("PersonA")
        seat5 = _FakeSeat("PersonB")
        ctrl, w = _ctrl_stub(
            seats={"3": seat3, "5": seat5},
            seat_names={"3": "PersonA", "5": "PersonB"},
        )
        with patch("ui.seat_names_mixin.save_names_data"), \
             patch("ui.seat_names_mixin.GoButton", _FakeSeat), \
             patch("ui.seat_names_mixin.SpecialDragButton", _FakeSeat):
            SeatNamesController._clear_all_seats(ctrl)
        assert seat3.assigned_name == ""
        assert seat5.assigned_name == ""

    def test_saves_names_data(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data") as mock_save:
            SeatNamesController._clear_all_seats(ctrl)
        mock_save.assert_called_once()

    def test_syncs_assigned_to_panel(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA"})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._clear_all_seats(ctrl)
        w._names_panel.set_assigned.assert_called_once()

    def test_no_error_when_no_seats(self):
        ctrl, w = _ctrl_stub(seat_names={})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._clear_all_seats(ctrl)  # must not raise
        assert w._seat_names == {}


# ══════════════════════════════════════════════════════════════════════════════
#  _sync_assigned_to_panel
# ══════════════════════════════════════════════════════════════════════════════

class TestSyncAssignedToPanel:
    """_sync_assigned_to_panel passes current seat name values to NamesPanel."""

    def test_passes_correct_assigned_set(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA", "5": "PersonB"})
        SeatNamesController._sync_assigned_to_panel(ctrl)
        w._names_panel.set_assigned.assert_called_once_with({"PersonA", "PersonB"})

    def test_passes_empty_set_when_no_names(self):
        ctrl, w = _ctrl_stub(seat_names={})
        SeatNamesController._sync_assigned_to_panel(ctrl)
        w._names_panel.set_assigned.assert_called_once_with(set())


# ══════════════════════════════════════════════════════════════════════════════
#  undo_last_assignment (A2)
# ══════════════════════════════════════════════════════════════════════════════

class TestUndoLastAssignment:
    """undo_last_assignment restores the seat state before the last mutation."""

    def test_empty_stack_returns_false(self):
        ctrl, _ = _ctrl_stub(seat_names={"3": "PersonA"})
        assert ctrl.undo_last_assignment() is False

    def test_undo_reverts_assignment(self):
        ctrl, w = _ctrl_stub(seat_names={})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "PersonA")
            assert w._seat_names == {"5": "PersonA"}
            ctrl.undo_last_assignment()
        assert w._seat_names == {}

    def test_undo_reverts_clear_all(self):
        ctrl, w = _ctrl_stub(seat_names={"3": "PersonA", "5": "PersonB"})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._clear_all_seats(ctrl)
            assert w._seat_names == {}
            ctrl.undo_last_assignment()
        assert w._seat_names == {"3": "PersonA", "5": "PersonB"}

    def test_undo_restores_seat_button_label(self):
        seat5 = _FakeSeat("")
        ctrl, w = _ctrl_stub(seats={"5": seat5}, seat_names={})
        with patch("ui.seat_names_mixin.save_names_data"), \
             patch("ui.seat_names_mixin.GoButton", _FakeSeat), \
             patch("ui.seat_names_mixin.SpecialDragButton", _FakeSeat):
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "PersonA")
            seat5.set_name("PersonA", emit_signal=False)  # simulate drag label
            ctrl.undo_last_assignment()
        assert seat5.assigned_name == ""

    def test_undo_is_multi_level(self):
        ctrl, w = _ctrl_stub(seat_names={})
        with patch("ui.seat_names_mixin.save_names_data"):
            SeatNamesController._on_seat_name_assigned(ctrl, 5, "PersonA")
            SeatNamesController._on_seat_name_assigned(ctrl, 6, "PersonB")
            ctrl.undo_last_assignment()          # undo PersonB
            assert w._seat_names == {"5": "PersonA"}
            ctrl.undo_last_assignment()          # undo PersonA
            assert w._seat_names == {}

    def test_undo_depth_is_capped(self):
        ctrl, w = _ctrl_stub(seat_names={})
        with patch("ui.seat_names_mixin.save_names_data"):
            for i in range(SeatNamesController._UNDO_DEPTH + 10):
                SeatNamesController._on_seat_name_assigned(ctrl, i, f"P{i}")
        assert len(ctrl._undo_stack) == SeatNamesController._UNDO_DEPTH
