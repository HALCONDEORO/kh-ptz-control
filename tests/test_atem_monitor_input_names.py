#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_atem_monitor_input_names.py -- Unit tests for ATEMMonitor._read_input_names
#                                           and _poll_pip initial-state behaviour.
from __future__ import annotations
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock


# -- Qt stubs (before importing atem_monitor) ---------------------------------
def _ensure_qt_stubs():
    for mod_name in ("PyQt5", "PyQt5.QtCore"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)
    qtc = sys.modules["PyQt5.QtCore"]
    if not hasattr(qtc, "QThread"):
        class _FakeQThread:
            def __init__(self, parent=None): pass
            def isInterruptionRequested(self): return False
        qtc.QThread = _FakeQThread
    if not hasattr(qtc, "pyqtSignal"):
        qtc.pyqtSignal = lambda *a, **kw: MagicMock()
    for attr in ("Qt", "QTimer"):
        if not hasattr(qtc, attr):
            setattr(qtc, attr, MagicMock())

_ensure_qt_stubs()

from adapters.atem_monitor import ATEMMonitor  # noqa: E402


# -- helpers ------------------------------------------------------------------
def _make_monitor():
    m = ATEMMonitor.__new__(ATEMMonitor)
    m._pip_enabled = None
    m.pip_changed = MagicMock()
    return m


class _FakeSource:
    """Minimal stand-in for a PyATEMMax ATEMVideoSources enum member."""
    def __init__(self, v): self._v = v
    def __eq__(self, o): return isinstance(o, _FakeSource) and self._v == o._v
    def __hash__(self): return hash(self._v)
    def __int__(self): return self._v
    def __repr__(self): return f"FakeSource({self._v})"


def _make_atem_and_mod(input_names):
    """Build a fake (atem, Mod) pair for _read_input_names tests.

    ATEMVideoSources is now an iterable list of _FakeSource objects — matching
    how the production code uses it (list(PyATEMMax.ATEMVideoSources)).
    """
    sources = []
    props = {}
    for iid, name in input_names.items():
        fs = _FakeSource(iid)
        sources.append(fs)
        props[fs] = SimpleNamespace(longName=name, shortName=(name[:4] if name else ""))

    class Mod:
        ATEMVideoSources = sources  # iterable — matches new _read_input_names API

    return SimpleNamespace(inputProperties=props), Mod


# -- TestReadInputNames -------------------------------------------------------
class TestReadInputNames:
    def test_reads_all_four_named_inputs(self):
        m = _make_monitor()
        atem, mod = _make_atem_and_mod({1: "PC", 2: "Platform", 3: "Comments", 4: "None"})
        assert m._read_input_names(atem, mod) == {1: "PC", 2: "Platform", 3: "Comments", 4: "None"}

    def test_strips_whitespace(self):
        m = _make_monitor()
        atem, mod = _make_atem_and_mod({1: "  PC  ", 2: "  Platform  "})
        result = m._read_input_names(atem, mod)
        assert result[1] == "PC" and result[2] == "Platform"

    def test_skips_empty_names(self):
        m = _make_monitor()
        atem, mod = _make_atem_and_mod({1: "PC", 2: "", 3: "Comments"})
        result = m._read_input_names(atem, mod)
        assert 1 in result and 2 not in result and 3 in result

    def test_falls_back_to_short_name(self):
        m = _make_monitor()
        fs2 = _FakeSource(2)
        prop = SimpleNamespace(longName=None, shortName="PLT")
        atem = SimpleNamespace(inputProperties={fs2: prop})
        class Mod:
            ATEMVideoSources = [fs2]  # iterable with one entry
        result = m._read_input_names(atem, Mod)
        assert result.get(2) == "PLT"

    def test_returns_empty_when_enum_raises(self):
        """Si list(ATEMVideoSources) lanza, devuelve {}."""
        m = _make_monitor()
        class BrokenMod:
            class ATEMVideoSources:
                def __iter__(self): raise ValueError("broken enum")
        result = m._read_input_names(SimpleNamespace(inputProperties={}), BrokenMod)
        assert result == {}

    def test_partial_failure_returns_good_inputs(self):
        """Los inputs que fallan al leer inputProperties se omiten; el resto se devuelve."""
        m = _make_monitor()
        sources = [_FakeSource(i) for i in range(1, 5)]
        prop = SimpleNamespace(longName="OK", shortName="OK")

        def _getitem(key):
            if int(key) == 2:
                raise KeyError("no input 2")
            return prop

        atem = SimpleNamespace(inputProperties=MagicMock(__getitem__=lambda s, k: _getitem(k)))

        class Mod:
            ATEMVideoSources = sources  # fuentes 1-4; la 2 falla al acceder

        result = m._read_input_names(atem, Mod)
        assert 2 not in result
        assert len(result) == len(sources) - 1  # 3 de 4


# -- TestPollPipInitialState --------------------------------------------------
class TestPollPipInitialState:
    def _atem(self, *, enabled, source=None):
        return SimpleNamespace(pictureInPicture=[SimpleNamespace(enabled=enabled, source=source)])

    def test_no_event_on_first_poll_pip_off(self):
        m = _make_monitor()
        m._poll_pip(self._atem(enabled=False))
        m.pip_changed.emit.assert_not_called()

    def test_state_initialised_after_off_poll(self):
        m = _make_monitor()
        m._poll_pip(self._atem(enabled=False))
        assert m._pip_enabled is False

    def test_event_on_first_poll_pip_on(self):
        m = _make_monitor()
        m._poll_pip(self._atem(enabled=True, source=2))
        m.pip_changed.emit.assert_called_once()

    def test_event_when_pip_turns_on_after_quiet_init(self):
        m = _make_monitor()
        m._poll_pip(self._atem(enabled=False))
        m.pip_changed.emit.assert_not_called()
        m._poll_pip(self._atem(enabled=True, source=3))
        m.pip_changed.emit.assert_called_once()

    def test_no_duplicate_event_pip_stays_off(self):
        m = _make_monitor()
        for _ in range(3):
            m._poll_pip(self._atem(enabled=False))
        m.pip_changed.emit.assert_not_called()

    def test_no_duplicate_event_pip_stays_on(self):
        m = _make_monitor()
        m._poll_pip(self._atem(enabled=True))
        m._poll_pip(self._atem(enabled=True))
        assert m.pip_changed.emit.call_count == 1

    def test_event_when_pip_turns_off(self):
        m = _make_monitor()
        m._poll_pip(self._atem(enabled=True))
        m.pip_changed.emit.reset_mock()
        m._poll_pip(self._atem(enabled=False))
        m.pip_changed.emit.assert_called_once()

    def test_exception_swallowed(self):
        m = _make_monitor()
        m._poll_pip(SimpleNamespace(pictureInPicture=None))
        m.pip_changed.emit.assert_not_called()

