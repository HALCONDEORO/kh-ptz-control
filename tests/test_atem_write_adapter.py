#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# tests/test_atem_write_adapter.py — Unit tests for ATEMWriteAdapter
#
# All tests use a mocked PyATEMMax — no real ATEM hardware required.

from __future__ import annotations

from unittest.mock import MagicMock, patch


from adapters.atem_write_adapter import ATEMWriteAdapter
from domain.ports import SwitcherStatus


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_adapter(ip="192.168.1.240"):
    return ATEMWriteAdapter(ip=ip)


def _mock_pyatemmax(program=1, preview=2, connect_ok=True):
    """Return a (module_mock, atem_instance_mock) pair.

    videoSource is set to a plain int so that int(mock.videoSource) works
    without relying on __int__ dunder on a MagicMock instance (which Python
    only dispatches via the type, not the instance).
    """
    atem_inst = MagicMock()
    atem_inst.waitForConnection.return_value = connect_ok
    # Plain int — int(atem_inst.programInput[0].videoSource) just works.
    atem_inst.programInput.__getitem__.return_value.videoSource = program
    atem_inst.previewInput.__getitem__.return_value.videoSource = preview

    mod = MagicMock()
    mod.ATEMMax.return_value = atem_inst
    mod.ATEMVideoSources = lambda x: x
    return mod, atem_inst


def _connected_adapter(ip="192.168.1.240", program=1, preview=2):
    """Return an adapter that is already connected (mocked)."""
    mod, inst = _mock_pyatemmax(program=program, preview=preview)
    adapter = _make_adapter(ip=ip)
    with patch.dict("sys.modules", {"PyATEMMax": mod}):
        adapter.connect()
    return adapter, inst, mod


# ── connect() ────────────────────────────────────────────────────────────────

class TestConnect:
    def test_returns_true_when_pyatemmax_connects(self):
        mod, inst = _mock_pyatemmax(connect_ok=True)
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            assert adapter.connect() is True
        assert adapter._connected is True

    def test_returns_false_when_timeout(self):
        mod, inst = _mock_pyatemmax(connect_ok=False)
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            assert adapter.connect() is False
        assert adapter._connected is False

    def test_returns_false_when_pyatemmax_missing(self):
        # sys.modules[name] = None causes `import name` to raise ImportError
        # without patching builtins.__import__ globally.
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"PyATEMMax": None}):
            result = adapter.connect()
        assert result is False
        assert adapter._connected is False

    def test_returns_false_when_ip_empty(self):
        adapter = _make_adapter(ip="")
        assert adapter.connect() is False

    def test_noop_when_already_connected(self):
        mod, inst = _mock_pyatemmax()
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            adapter.connect()
            adapter.connect()   # second call — must short-circuit
        assert mod.ATEMMax.call_count == 1  # only one TCP connection opened

    def test_connect_exception_returns_false(self):
        mod = MagicMock()
        mod.ATEMMax.side_effect = RuntimeError("network error")
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            assert adapter.connect() is False

    def test_connect_exception_closes_atem_object(self):
        """Socket must be closed when waitForConnection raises."""
        mod, inst = _mock_pyatemmax()
        inst.waitForConnection.side_effect = RuntimeError("network error")
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            adapter.connect()
        inst.disconnect.assert_called_once()

    def test_connect_timeout_closes_atem_object(self):
        """Socket must be closed when connection times out (no response)."""
        mod, inst = _mock_pyatemmax(connect_ok=False)
        adapter = _make_adapter()
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            adapter.connect()
        inst.disconnect.assert_called_once()


# ── connect_async() ──────────────────────────────────────────────────────────

class TestConnectAsync:
    def test_connect_async_sets_connected(self):
        mod, inst = _mock_pyatemmax()
        adapter = _make_adapter()
        import threading
        done = threading.Event()
        original = adapter._connect_thread
        def patched():
            original()
            done.set()
        adapter._connect_thread = patched
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            adapter.connect_async()
            done.wait(timeout=3)
        assert adapter._connected is True

    def test_connect_async_no_double_thread(self):
        """Second connect_async() while _connecting=True must be a no-op."""
        mod, inst = _mock_pyatemmax()
        adapter = _make_adapter()
        import threading
        barrier = threading.Barrier(2)
        spawns = []
        original = adapter._connect_thread
        def slow():
            spawns.append(1)
            barrier.wait(timeout=3)
            original()
        adapter._connect_thread = slow
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            t = threading.Thread(target=adapter.connect_async, daemon=True)
            t.start()
            barrier.wait(timeout=3)
            adapter.connect_async()   # second call while first thread running
        assert len(spawns) == 1       # only one thread was dispatched

    def test_connecting_flag_cleared_on_failure(self):
        mod, inst = _mock_pyatemmax(connect_ok=False)
        adapter = _make_adapter()
        import threading
        done = threading.Event()
        original = adapter._connect_thread
        def patched():
            original()
            done.set()
        adapter._connect_thread = patched
        with patch.dict("sys.modules", {"PyATEMMax": mod}):
            adapter.connect_async()
            done.wait(timeout=3)
        assert adapter._connecting is False  # must clear even on failure


# ── disconnect() ─────────────────────────────────────────────────────────────

class TestDisconnect:
    def test_disconnect_marks_not_connected(self):
        adapter, inst, _ = _connected_adapter()
        adapter.disconnect()
        assert adapter._connected is False
        assert adapter._atem is None

    def test_disconnect_calls_atem_disconnect(self):
        adapter, inst, _ = _connected_adapter()
        adapter.disconnect()
        inst.disconnect.assert_called_once()

    def test_disconnect_when_not_connected_is_safe(self):
        adapter = _make_adapter()
        adapter.disconnect()  # must not raise


# ── get_program_input / get_preview_input ────────────────────────────────────

class TestReadMethods:
    def test_get_program_input_returns_int(self):
        adapter, _, _ = _connected_adapter(program=3)
        assert adapter.get_program_input() == 3

    def test_get_preview_input_returns_int(self):
        adapter, _, _ = _connected_adapter(preview=2)
        assert adapter.get_preview_input() == 2

    def test_get_program_input_returns_none_when_not_connected(self):
        assert _make_adapter().get_program_input() is None

    def test_get_preview_input_returns_none_when_not_connected(self):
        assert _make_adapter().get_preview_input() is None

    def test_transient_read_error_does_not_disconnect(self):
        """A poll failure must not tear down the TCP connection."""
        adapter, inst, _ = _connected_adapter()
        inst.programInput.__getitem__.side_effect = RuntimeError("transient")
        result = adapter.get_program_input()
        assert result is None
        assert adapter._connected is True   # still connected

    def test_get_status_connected(self):
        adapter, _, _ = _connected_adapter(program=1, preview=2)
        status = adapter.get_status()
        assert isinstance(status, SwitcherStatus)
        assert status.connected is True
        assert status.adapter_type == "atem"

    def test_get_status_disconnected(self):
        status = _make_adapter().get_status()
        assert status.connected is False
        assert status.adapter_type == "atem"


# ── test_connection() ────────────────────────────────────────────────────────

class TestTestConnection:
    def test_success_when_connected(self):
        adapter, _, _ = _connected_adapter(program=1)
        result = adapter.test_connection()
        assert result.ok is True
        assert result.command == "test_connection"

    def test_failure_when_not_connected(self):
        result = _make_adapter(ip="").test_connection()
        assert result.ok is False
        assert result.error_code == "DISCONNECTED"


# ── set_preview_input() ──────────────────────────────────────────────────────

class TestSetPreviewInput:
    def test_calls_setPreviewInputVideoSource(self):
        adapter, inst, _ = _connected_adapter()
        result = adapter.set_preview_input(2)
        assert result.ok is True
        assert result.command == "set_preview_input"
        assert result.target == 2
        inst.setPreviewInputVideoSource.assert_called_once_with(0, 2)

    def test_failure_when_not_connected(self):
        result = _make_adapter(ip="").set_preview_input(2)
        assert result.ok is False
        assert result.error_code == "DISCONNECTED"
        assert result.target == 2

    def test_failure_on_pyatemmax_exception(self):
        adapter, inst, _ = _connected_adapter()
        inst.setPreviewInputVideoSource.side_effect = RuntimeError("bus error")
        result = adapter.set_preview_input(1)
        assert result.ok is False
        assert result.error_code == "ERROR"


# ── cut() ─────────────────────────────────────────────────────────────────────

class TestCut:
    def test_calls_execCutME(self):
        adapter, inst, _ = _connected_adapter()
        result = adapter.cut()
        assert result.ok is True
        assert result.command == "cut"
        inst.execCutME.assert_called_once_with(0)

    def test_failure_when_not_connected(self):
        result = _make_adapter(ip="").cut()
        assert result.ok is False
        assert result.error_code == "DISCONNECTED"

    def test_failure_on_exception(self):
        adapter, inst, _ = _connected_adapter()
        inst.execCutME.side_effect = RuntimeError("timeout")
        result = adapter.cut()
        assert result.ok is False
        assert result.error_code == "ERROR"

    def test_no_retry_on_failure(self):
        """cut() must not retry — one call, one result (safety contract)."""
        adapter, inst, _ = _connected_adapter()
        inst.execCutME.side_effect = RuntimeError("fail")
        adapter.cut()
        assert inst.execCutME.call_count == 1


# ── auto() ────────────────────────────────────────────────────────────────────

class TestAuto:
    def test_calls_execAutoME(self):
        adapter, inst, _ = _connected_adapter()
        result = adapter.auto()
        assert result.ok is True
        assert result.command == "auto"
        inst.execAutoME.assert_called_once_with(0)

    def test_failure_when_not_connected(self):
        result = _make_adapter(ip="").auto()
        assert result.ok is False
        assert result.error_code == "DISCONNECTED"

    def test_failure_on_exception(self):
        adapter, inst, _ = _connected_adapter()
        inst.execAutoME.side_effect = RuntimeError("timeout")
        result = adapter.auto()
        assert result.ok is False
        assert result.error_code == "ERROR"

    def test_no_retry_on_failure(self):
        adapter, inst, _ = _connected_adapter()
        inst.execAutoME.side_effect = RuntimeError("fail")
        adapter.auto()
        assert inst.execAutoME.call_count == 1


# ── set_pip_enabled() ────────────────────────────────────────────────────────

class TestSetPipEnabled:
    def test_calls_setPIPEnabled_when_available(self):
        adapter, inst, _ = _connected_adapter()
        # MagicMock auto-creates the attribute — hasattr returns True
        result = adapter.set_pip_enabled(True)
        assert result.ok is True
        assert result.command == "set_pip_enabled"
        inst.setPIPEnabled.assert_called_once_with(0, True)

    def test_falls_back_to_setPictureInPictureEnabled(self):
        adapter, inst, _ = _connected_adapter()
        del inst.setPIPEnabled           # remove from mock so hasattr=False
        result = adapter.set_pip_enabled(True)
        assert result.ok is True
        inst.setPictureInPictureEnabled.assert_called_once_with(0, True)

    def test_api_not_found_does_not_disconnect(self):
        """AttributeError from missing PiP method must NOT tear down connection."""
        adapter, inst, _ = _connected_adapter()
        # Make both methods absent
        del inst.setPIPEnabled
        del inst.setPictureInPictureEnabled
        result = adapter.set_pip_enabled(True)
        assert result.ok is False
        assert result.error_code == "API_NOT_FOUND"
        assert adapter._connected is True   # still connected

    def test_failure_when_not_connected(self):
        result = _make_adapter(ip="").set_pip_enabled(True)
        assert result.ok is False
        assert result.error_code == "DISCONNECTED"

    def test_network_error_disconnects(self):
        adapter, inst, _ = _connected_adapter()
        inst.setPIPEnabled.side_effect = OSError("broken pipe")
        result = adapter.set_pip_enabled(True)
        assert result.ok is False
        assert result.error_code == "ERROR"
        assert adapter._connected is False   # network error does disconnect


# ── AtemWritePort protocol compliance ────────────────────────────────────────

class TestProtocolCompliance:
    def test_has_all_write_methods(self):
        adapter = _make_adapter()
        for method in ("connect", "disconnect", "get_program_input",
                       "get_preview_input", "test_connection", "get_status",
                       "set_preview_input", "cut", "auto", "set_pip_enabled"):
            assert callable(getattr(adapter, method, None)), f"missing: {method}"

    def test_satisfies_atem_write_port_protocol(self):
        from ports.atem_port import AtemWritePort, AtemReadPort
        adapter = _make_adapter()
        assert isinstance(adapter, AtemReadPort), "ATEMWriteAdapter must satisfy AtemReadPort"
        assert isinstance(adapter, AtemWritePort), "ATEMWriteAdapter must satisfy AtemWritePort"
