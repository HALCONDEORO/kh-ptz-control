#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
ATEM simulator QA tests — #752.

Covers FakeATEM Phase 1 behaviour: Program, Preview, CUT, AUTO,
disconnect/reconnect, command results, callbacks and runtime wiring.

Hardware-free: no sockets, no Qt, no production files.
"""
from __future__ import annotations

import socket


from adapters.fake_atem import FakeATEM
from domain.ports import AtemCommandResult, AtemPort


# ── Helpers ───────────────────────────────────────────────────────────────────

def _connected() -> FakeATEM:
    a = FakeATEM()
    a.connect()
    return a


# ── Contract ──────────────────────────────────────────────────────────────────

class TestFakeATEMIsAtemPort:
    def test_is_atem_port(self):
        assert isinstance(FakeATEM(), AtemPort)

    def test_adapter_type_is_fake(self):
        assert FakeATEM().get_status().adapter_type == "fake"

    def test_initial_not_connected(self):
        assert FakeATEM().get_status().connected is False

    def test_initial_program_none(self):
        assert FakeATEM().get_program_input() is None

    def test_initial_preview_none(self):
        assert FakeATEM().get_preview_input() is None

    def test_initial_not_transitioning(self):
        assert FakeATEM().get_status().transitioning is False


# ── Connect / disconnect ──────────────────────────────────────────────────────

class TestConnect:
    def test_connect_returns_true(self):
        assert FakeATEM().connect() is True

    def test_connect_sets_connected(self):
        a = FakeATEM()
        a.connect()
        assert a.get_status().connected is True

    def test_disconnect_clears_connected(self):
        a = _connected()
        a.disconnect()
        assert a.get_status().connected is False

    def test_no_sockets_opened(self, monkeypatch):

        def _fail(*args, **kwargs):
            raise AssertionError("FakeATEM must not open sockets")

        monkeypatch.setattr(socket.socket, "connect", _fail)
        a = FakeATEM()
        a.connect()
        a.disconnect()


# ── test_connection ───────────────────────────────────────────────────────────

class TestTestConnection:
    def test_returns_ok_when_connected(self):
        result = _connected().test_connection()
        assert result.ok is True
        assert result.command == "test_connection"

    def test_returns_failure_when_disconnected(self):
        result = FakeATEM().test_connection()
        assert result.ok is False
        assert result.error_code == "NOT_CONNECTED"

    def test_result_has_correlation_id(self):
        result = _connected().test_connection()
        assert result.correlation_id
        assert len(result.correlation_id) > 0

    def test_result_has_duration_ms(self):
        result = _connected().test_connection()
        assert result.duration_ms >= 0.0


# ── set_preview_input ─────────────────────────────────────────────────────────

class TestSetPreviewInput:
    def test_updates_preview_state(self):
        a = _connected()
        a.set_preview_input(2)
        assert a.get_preview_input() == 2

    def test_returns_success(self):
        result = _connected().set_preview_input(1)
        assert result.ok is True
        assert result.target == 1

    def test_does_not_change_program(self):
        a = _connected()
        a.set_program_input(1)
        a.set_preview_input(3)
        assert a.get_program_input() == 1

    def test_fails_when_disconnected(self):
        result = FakeATEM().set_preview_input(2)
        assert result.ok is False
        assert result.error_code == "NOT_CONNECTED"

    def test_same_input_idempotent(self):
        a = _connected()
        a.set_preview_input(2)
        received: list[int] = []
        a.add_preview_changed_callback(received.append)
        a.set_preview_input(2)  # same — no callback
        assert received == []

    def test_different_input_fires_callback(self):
        a = _connected()
        received: list[int] = []
        a.add_preview_changed_callback(received.append)
        a.set_preview_input(3)
        assert received == [3]


# ── CUT ───────────────────────────────────────────────────────────────────────

class TestCut:
    def test_copies_preview_to_program(self):
        a = _connected()
        a.set_preview_input(2)
        a.cut()
        assert a.get_program_input() == 2

    def test_returns_success(self):
        a = _connected()
        a.set_preview_input(3)
        result = a.cut()
        assert result.ok is True
        assert result.command == "cut"
        assert result.target == 3

    def test_fires_program_callback(self):
        a = _connected()
        a.set_preview_input(2)
        received: list[int] = []
        a.add_program_changed_callback(received.append)
        a.cut()
        assert received == [2]

    def test_fails_when_disconnected(self):
        result = FakeATEM().cut()
        assert result.ok is False
        assert result.error_code == "NOT_CONNECTED"

    def test_fails_when_no_preview_set(self):
        result = _connected().cut()
        assert result.ok is False
        assert result.error_code == "NO_PREVIEW"

    def test_no_callback_when_same_program(self):
        a = _connected()
        a.set_program_input(2)
        a.set_preview_input(2)
        received: list[int] = []
        a.add_program_changed_callback(received.append)
        a.cut()
        assert received == []  # same input — debounced


# ── AUTO ──────────────────────────────────────────────────────────────────────

class TestAuto:
    def test_copies_preview_to_program(self):
        a = _connected()
        a.set_preview_input(3)
        a.auto()
        assert a.get_program_input() == 3

    def test_returns_success(self):
        a = _connected()
        a.set_preview_input(1)
        result = a.auto()
        assert result.ok is True
        assert result.command == "auto"
        assert result.target == 1

    def test_fires_program_callback(self):
        a = _connected()
        a.set_preview_input(3)
        received: list[int] = []
        a.add_program_changed_callback(received.append)
        a.auto()
        assert received == [3]

    def test_transitioning_ends_after_auto(self):
        a = _connected()
        a.set_preview_input(2)
        a.auto()
        assert a.get_status().transitioning is False

    def test_fails_when_disconnected(self):
        result = FakeATEM().auto()
        assert result.ok is False
        assert result.error_code == "NOT_CONNECTED"

    def test_fails_when_no_preview_set(self):
        result = _connected().auto()
        assert result.ok is False
        assert result.error_code == "NO_PREVIEW"


# ── Connection changed callbacks ──────────────────────────────────────────────

class TestConnectionCallbacks:
    def test_connect_fires_connection_callback_true(self):
        a = FakeATEM()
        received: list[bool] = []
        a.add_connection_changed_callback(received.append)
        a.connect()
        assert received == [True]

    def test_disconnect_fires_connection_callback_false(self):
        a = _connected()
        received: list[bool] = []
        a.add_connection_changed_callback(received.append)
        a.disconnect()
        assert received == [False]

    def test_connect_already_connected_no_duplicate_callback(self):
        a = _connected()
        received: list[bool] = []
        a.add_connection_changed_callback(received.append)
        a.connect()  # already connected — no callback
        assert received == []

    def test_remove_connection_callback(self):
        a = FakeATEM()
        received: list[bool] = []
        cb = received.append
        a.add_connection_changed_callback(cb)
        a.remove_connection_changed_callback(cb)
        a.connect()
        assert received == []


# ── Preview changed callbacks ─────────────────────────────────────────────────

class TestPreviewCallbacks:
    def test_preview_changed_on_set_preview(self):
        a = _connected()
        received: list[int] = []
        a.add_preview_changed_callback(received.append)
        a.set_preview_input(2)
        assert received == [2]

    def test_remove_preview_callback(self):
        a = _connected()
        received: list[int] = []
        cb = received.append
        a.add_preview_changed_callback(cb)
        a.remove_preview_changed_callback(cb)
        a.set_preview_input(3)
        assert received == []

    def test_multiple_preview_callbacks_all_called(self):
        a = _connected()
        x: list[int] = []
        y: list[int] = []
        a.add_preview_changed_callback(x.append)
        a.add_preview_changed_callback(y.append)
        a.set_preview_input(4)
        assert x == [4]
        assert y == [4]

    def test_faulty_preview_callback_does_not_crash(self):
        a = _connected()

        def bad(v):
            raise RuntimeError("boom")

        good: list[int] = []
        a.add_preview_changed_callback(bad)
        a.add_preview_changed_callback(good.append)
        a.set_preview_input(1)
        assert good == [1]


# ── AtemCommandResult ─────────────────────────────────────────────────────────

class TestAtemCommandResult:
    def test_success_factory(self):
        r = AtemCommandResult.success("cut", target=2)
        assert r.ok is True
        assert r.command == "cut"
        assert r.target == 2

    def test_failure_factory(self):
        r = AtemCommandResult.failure("cut", "NOT_CONNECTED", "disconnected")
        assert r.ok is False
        assert r.error_code == "NOT_CONNECTED"
        assert r.message == "disconnected"

    def test_unique_correlation_ids(self):
        r1 = AtemCommandResult.success("cut")
        r2 = AtemCommandResult.success("cut")
        assert r1.correlation_id != r2.correlation_id

    def test_last_command_result_stored(self):
        a = _connected()
        a.set_preview_input(1)
        a.cut()
        assert a.last_command_result is not None
        assert a.last_command_result.command == "cut"


# ── SwitcherStatus new fields ─────────────────────────────────────────────────

class TestSwitcherStatusNewFields:
    def test_preview_input_in_status(self):
        a = _connected()
        a.set_preview_input(3)
        assert a.get_status().preview_input == 3

    def test_transitioning_false_at_rest(self):
        a = _connected()
        assert a.get_status().transitioning is False

    def test_preview_input_initially_none(self):
        assert FakeATEM().get_status().preview_input is None


# ── Legacy set_program_input path ─────────────────────────────────────────────

class TestLegacyProgramInput:
    def test_set_program_input_updates_state(self):
        a = FakeATEM()
        a.set_program_input(2)
        assert a.get_program_input() == 2

    def test_repeated_same_input_debounced(self):
        a = FakeATEM()
        received: list[int] = []
        a.add_program_changed_callback(received.append)
        a.set_program_input(1)
        a.set_program_input(1)
        assert received == [1]

    def test_different_inputs_both_fire(self):
        a = FakeATEM()
        received: list[int] = []
        a.add_program_changed_callback(received.append)
        a.set_program_input(1)
        a.set_program_input(2)
        assert received == [1, 2]

