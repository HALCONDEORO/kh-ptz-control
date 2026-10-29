# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for adapters/fake_atem.py — FakeATEM adapter (#297)."""
from __future__ import annotations


from adapters.fake_atem import FakeATEM
from domain.ports import AtemPort, SwitcherPort, SwitcherStatus


def _atem() -> FakeATEM:
    return FakeATEM()


class TestFakeATEMIsPort:
    def test_is_switcher_port(self):
        assert isinstance(_atem(), SwitcherPort)

    def test_is_atem_port(self):
        assert isinstance(_atem(), AtemPort)

    def test_adapter_type_is_fake(self):
        assert _atem().get_status().adapter_type == "fake"

    def test_initial_not_connected(self):
        assert _atem().get_status().connected is False

    def test_initial_program_input_none(self):
        assert _atem().get_program_input() is None


class TestFakeATEMConnect:
    def test_connect_returns_true(self):
        assert _atem().connect() is True

    def test_connect_sets_connected(self):
        atem = _atem()
        atem.connect()
        assert atem.get_status().connected is True

    def test_disconnect_clears_connected(self):
        atem = _atem()
        atem.connect()
        atem.disconnect()
        assert atem.get_status().connected is False


class TestFakeATEMProgramInput:
    def test_set_program_input_updates_state(self):
        atem = _atem()
        atem.set_program_input(2)
        assert atem.get_program_input() == 2

    def test_set_program_input_reflected_in_status(self):
        atem = _atem()
        atem.set_program_input(3)
        assert atem.get_status().program_input == 3

    def test_repeated_same_input_debounced(self):
        atem = _atem()
        received: list[int] = []
        atem.add_program_changed_callback(received.append)
        atem.set_program_input(1)
        atem.set_program_input(1)  # same — should be ignored
        assert received == [1]

    def test_different_inputs_both_fire(self):
        atem = _atem()
        received: list[int] = []
        atem.add_program_changed_callback(received.append)
        atem.set_program_input(1)
        atem.set_program_input(2)
        assert received == [1, 2]


class TestFakeATEMCallbacks:
    def test_callback_receives_input(self):
        atem = _atem()
        received: list[int] = []
        atem.add_program_changed_callback(received.append)
        atem.set_program_input(5)
        assert received == [5]

    def test_multiple_callbacks_all_called(self):
        atem = _atem()
        a: list[int] = []
        b: list[int] = []
        atem.add_program_changed_callback(a.append)
        atem.add_program_changed_callback(b.append)
        atem.set_program_input(4)
        assert a == [4]
        assert b == [4]

    def test_remove_callback_stops_events(self):
        atem = _atem()
        received: list[int] = []
        atem.add_program_changed_callback(received.append)
        atem.set_program_input(1)
        atem.remove_program_changed_callback(received.append)
        atem.set_program_input(2)
        assert received == [1]

    def test_add_same_callback_twice_only_registered_once(self):
        atem = _atem()
        received: list[int] = []
        cb = received.append
        atem.add_program_changed_callback(cb)
        atem.add_program_changed_callback(cb)
        atem.set_program_input(7)
        assert received == [7]

    def test_faulty_callback_does_not_crash(self):
        atem = _atem()

        def bad_cb(inp):
            raise RuntimeError("boom")

        good_received: list[int] = []
        atem.add_program_changed_callback(bad_cb)
        atem.add_program_changed_callback(good_received.append)
        atem.set_program_input(3)
        assert good_received == [3]


class TestFakeATEMAutomation:
    def test_automation_mode_default_false(self):
        assert _atem().get_status().automation_mode is False

    def test_set_automation_mode_true(self):
        atem = _atem()
        atem.set_automation_mode(True)
        assert atem.get_status().automation_mode is True

    def test_constructor_automation_mode(self):
        atem = FakeATEM(automation_mode=True)
        assert atem.get_status().automation_mode is True


class TestFakeATEMStatus:
    def test_get_status_returns_switcher_status(self):
        assert isinstance(_atem().get_status(), SwitcherStatus)

    def test_no_network_calls(self, monkeypatch):
        """FakeATEM must never open sockets."""
        import socket

        def _fail(*args, **kwargs):
            raise AssertionError("FakeATEM must not open sockets")

        monkeypatch.setattr(socket.socket, "connect", _fail)
        atem = _atem()
        atem.connect()
        atem.set_program_input(1)
        atem.disconnect()
