# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for ports/atem_port.py — AtemReadPort and AtemWritePort protocols (#551)."""
from __future__ import annotations


from adapters.fake_atem import FakeATEM
from ports.atem_port import AtemReadPort, AtemWritePort


class TestAtemPortProtocols:
    def test_fake_atem_is_atem_read_port(self):
        assert isinstance(FakeATEM(), AtemReadPort)

    def test_fake_atem_is_atem_write_port(self):
        assert isinstance(FakeATEM(), AtemWritePort)

    def test_atem_write_port_is_subtype_of_read_port(self):
        a = FakeATEM()
        assert isinstance(a, AtemReadPort)
        assert isinstance(a, AtemWritePort)

    def test_read_port_methods_do_not_mutate(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(2)
        a.set_program_input(1)
        # Read-only operations — must not change state
        assert a.get_program_input() == 1
        assert a.get_preview_input() == 2
        result = a.test_connection()
        assert result.ok is True
        status = a.get_status()
        assert status.adapter_type == "fake"
        # State unchanged after reads
        assert a.get_program_input() == 1
        assert a.get_preview_input() == 2

    def test_write_port_cut_changes_program(self):
        a = FakeATEM()
        a.connect()
        a.set_preview_input(3)
        result = a.cut()
        assert result.ok is True
        assert a.get_program_input() == 3

    def test_write_port_set_preview_does_not_change_program(self):
        a = FakeATEM()
        a.connect()
        a.set_program_input(1)
        a.set_preview_input(2)
        assert a.get_program_input() == 1  # unchanged

