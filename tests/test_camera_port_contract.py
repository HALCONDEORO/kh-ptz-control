# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Contract tests for the CameraPort protocol.

Both FakeCameraPort and ViscaCameraAdapter must satisfy the same CameraPort
contract.  Adding a new adapter means adding it to the IMPLEMENTATIONS
fixture — every contract test runs against all implementations automatically.
"""

from __future__ import annotations

import pytest

from domain.ports import CameraStatus
from domain.supportability import CommandResult
from ports.camera_port import CameraPort, make_command_result
from adapters.fake_camera_port import FakeCameraPort


# ── Stubs for ViscaCameraAdapter tests ───────────────────────────────────────

class _StubWorker:
    def __init__(self):
        self.sent = []
        self.priority = []

    def send(self, cmd):
        self.sent.append(cmd)

    def send_priority(self, cmd):
        self.priority.append(cmd)


class _StubManager:
    def is_connected(self, ip: str) -> bool:
        w = self.workers.get(ip)
        return bool(w is not None and getattr(w, "connected", False))

    def __init__(self):
        self.workers: dict[str, _StubWorker] = {}
        self.invalidated: list[str] = []

    def worker(self, ip: str) -> _StubWorker:
        self.workers.setdefault(ip, _StubWorker())
        return self.workers[ip]

    def invalidate_zoom(self, ip: str) -> None:
        self.invalidated.append(ip)


_CAM_CONFIGS = {1: ("10.0.0.1", "81"), 2: ("10.0.0.2", "82")}


def _make_visca_adapter(default_ok: bool = True):
    """Return a ViscaCameraAdapter with a stub manager and patched _send_confirmed."""
    from adapters.visca_camera_adapter import ViscaCameraAdapter
    mgr = _StubManager()
    adapter = ViscaCameraAdapter(mgr, cam_configs=_CAM_CONFIGS)
    adapter._send_confirmed = lambda ip, cam_id, cmd: default_ok
    return adapter, mgr


# ── Protocol conformance ──────────────────────────────────────────────────────

class TestCameraPortProtocolConformance:
    """FakeCameraPort and ViscaCameraAdapter must be recognised as CameraPort."""

    def test_fake_camera_port_satisfies_protocol(self):
        port = FakeCameraPort()
        assert isinstance(port, CameraPort)

    def test_visca_camera_adapter_satisfies_protocol(self):
        adapter, _ = _make_visca_adapter()
        assert isinstance(adapter, CameraPort)


# ── Contract: all implementations must pass these tests ───────────────────────

@pytest.fixture(params=["fake", "visca"])
def port_and_cam(request):
    """Parametrised fixture returning (adapter, camera_id)."""
    if request.param == "fake":
        return FakeCameraPort(known_cameras={"cam1": "main"}), "cam1"
    if request.param == "visca":
        adapter, _ = _make_visca_adapter()
        return adapter, "cam1"
    raise ValueError(request.param)


class TestCameraPortContract:
    """Every implementation must fulfil the same behavioural contract."""

    def test_recall_preset_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.recall_preset(cam_id, 5)
        assert isinstance(result, CommandResult)

    def test_recall_preset_ok_true_on_success(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.recall_preset(cam_id, 5)
        assert result.ok is True

    def test_recall_preset_command_name(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.recall_preset(cam_id, 5)
        assert result.command == "recall_preset"

    def test_recall_preset_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.recall_preset(cam_id, 5)
        assert result.target == cam_id

    def test_recall_preset_has_correlation_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.recall_preset(cam_id, 5)
        assert result.correlation_id

    def test_save_preset_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.save_preset(cam_id, 3)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "save_preset"

    def test_move_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.move(cam_id, 5, -3)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "move"

    def test_stop_move_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.stop_move(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "stop_move"

    def test_zoom_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.zoom(cam_id, 3)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "zoom"

    def test_power_on_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.power_on(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "power_on"

    def test_standby_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.standby(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "standby"

    def test_home_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.home(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "home"

    def test_get_status_returns_camera_status(self, port_and_cam):
        port, cam_id = port_and_cam
        status = port.get_status(cam_id)
        assert isinstance(status, CameraStatus)

    def test_get_status_camera_id_matches(self, port_and_cam):
        port, cam_id = port_and_cam
        status = port.get_status(cam_id)
        assert status.camera_id == cam_id

    def test_result_correlation_ids_are_unique(self, port_and_cam):
        port, cam_id = port_and_cam
        r1 = port.recall_preset(cam_id, 1)
        r2 = port.recall_preset(cam_id, 2)
        assert r1.correlation_id != r2.correlation_id

    def test_error_result_has_error_code(self):
        """CommandResult with ok=False must have a non-empty error_code."""
        result = make_command_result(
            ok=False,
            command="recall_preset",
            camera_id="cam1",
            message="Camera timeout",
        )
        assert result.ok is False
        assert result.error_code  # must be non-empty

    def test_success_result_has_no_error_code(self):
        result = make_command_result(
            ok=True,
            command="recall_preset",
            camera_id="cam1",
        )
        assert result.ok is True
        assert result.error_code is None

    # ── Additional field-completeness assertions ──────────────────────────────

    def test_save_preset_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.save_preset(cam_id, 3)
        assert result.target == cam_id

    def test_move_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.move(cam_id, 3, 0)
        assert result.target == cam_id

    def test_stop_move_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.stop_move(cam_id)
        assert result.target == cam_id

    def test_zoom_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.zoom(cam_id, 2)
        assert result.target == cam_id

    def test_power_on_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.power_on(cam_id)
        assert result.target == cam_id

    def test_standby_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.standby(cam_id)
        assert result.target == cam_id

    def test_home_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.home(cam_id)
        assert result.target == cam_id

    def test_all_command_results_have_non_empty_correlation_id(self, port_and_cam):
        port, cam_id = port_and_cam
        for result in [
            port.move(cam_id, 1, 0),
            port.stop_move(cam_id),
            port.zoom(cam_id, 1),
            port.power_on(cam_id),
            port.standby(cam_id),
            port.home(cam_id),
        ]:
            assert result.correlation_id, f"Missing correlation_id on {result.command!r}"

    def test_get_status_adapter_type_is_non_empty(self, port_and_cam):
        port, cam_id = port_and_cam
        status = port.get_status(cam_id)
        assert status.adapter_type

    def test_get_status_connected_is_bool(self, port_and_cam):
        port, cam_id = port_and_cam
        status = port.get_status(cam_id)
        assert isinstance(status.connected, bool)

    # ── stop_all contract ─────────────────────────────────────────────────────

    def test_stop_all_returns_command_result(self, port_and_cam):
        port, _ = port_and_cam
        result = port.stop_all()
        assert isinstance(result, CommandResult)

    def test_stop_all_command_name(self, port_and_cam):
        port, _ = port_and_cam
        result = port.stop_all()
        assert result.command == "stop_all"

    def test_stop_all_ok_true(self, port_and_cam):
        port, _ = port_and_cam
        result = port.stop_all()
        assert result.ok is True

    def test_stop_all_has_correlation_id(self, port_and_cam):
        port, _ = port_and_cam
        result = port.stop_all()
        assert result.correlation_id

    # ── cancel_polls contract ─────────────────────────────────────────────────

    def test_cancel_polls_returns_command_result(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.cancel_polls(cam_id)
        assert isinstance(result, CommandResult)

    def test_cancel_polls_ok_true(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.cancel_polls(cam_id)
        assert result.ok is True

    def test_cancel_polls_command_name(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.cancel_polls(cam_id)
        assert result.command == "cancel_polls"

    def test_cancel_polls_target_is_camera_id(self, port_and_cam):
        port, cam_id = port_and_cam
        result = port.cancel_polls(cam_id)
        assert result.target == cam_id


# ── Disconnected-state contract ───────────────────────────────────────────────

@pytest.fixture(params=["fake_disconnected", "visca_disconnected"])
def port_and_cam_disconnected(request):
    """Parametrised fixture: both implementations with a failing hardware path."""
    if request.param == "fake_disconnected":
        # FakeCameraPort with connected=False for the camera — still succeeds
        # synchronously (fake is always offline-safe).
        port = FakeCameraPort()
        port._connected["cam1"] = False  # simulate disconnected flag
        return port, "cam1"
    if request.param == "visca_disconnected":
        adapter, _ = _make_visca_adapter(default_ok=False)  # _send_confirmed → False
        return adapter, "cam1"
    raise ValueError(request.param)


class TestCameraPortDisconnectedGraceful:
    """Both implementations must handle a disconnected/failing camera without
    raising exceptions — they must return a CommandResult (ok may be False for
    VISCA, True for Fake which is always synchronous) but must never propagate
    an unhandled exception to the caller.
    """

    def _assert_safe(self, result: "CommandResult") -> None:
        assert isinstance(result, CommandResult)
        # ok=False is acceptable; unhandled exception is not.

    def test_recall_preset_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.recall_preset(cam_id, 1))

    def test_save_preset_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.save_preset(cam_id, 1))

    def test_move_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.move(cam_id, 3, 0))

    def test_stop_move_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.stop_move(cam_id))

    def test_zoom_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.zoom(cam_id, 2))

    def test_power_on_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.power_on(cam_id))

    def test_standby_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.standby(cam_id))

    def test_home_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.home(cam_id))

    def test_stop_all_does_not_raise(self, port_and_cam_disconnected):
        port, _ = port_and_cam_disconnected
        self._assert_safe(port.stop_all())

    def test_cancel_polls_does_not_raise(self, port_and_cam_disconnected):
        port, cam_id = port_and_cam_disconnected
        self._assert_safe(port.cancel_polls(cam_id))

    def test_failed_command_has_error_code(self, port_and_cam_disconnected):
        """When a command genuinely fails (ok=False) the error_code must be set."""
        port, cam_id = port_and_cam_disconnected
        result = port.recall_preset(cam_id, 1)
        if not result.ok:
            assert result.error_code, "ok=False result must have a non-empty error_code"

    def test_stop_all_command_name_on_failure(self, port_and_cam_disconnected):
        port, _ = port_and_cam_disconnected
        result = port.stop_all()
        assert result.command == "stop_all"


# ── FakeCameraPort-specific tests ─────────────────────────────────────────────

class TestFakeCameraPortState:
    """FakeCameraPort-specific state inspection (not part of the protocol contract)."""

    def test_recall_preset_updates_current_preset(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 7)
        assert port.current_preset("cam1") == 7

    def test_home_resets_preset_to_zero(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 4)
        port.home("cam1")
        assert port.current_preset("cam1") == 0

    def test_power_on_sets_powered(self):
        port = FakeCameraPort()
        port.power_on("cam1")
        assert port.is_powered("cam1") is True

    def test_standby_clears_powered(self):
        port = FakeCameraPort()
        port.power_on("cam1")
        port.standby("cam1")
        assert port.is_powered("cam1") is False

    def test_move_sets_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        assert port.is_moving("cam1") is True

    def test_stop_move_clears_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 5, 0)
        port.stop_move("cam1")
        assert port.is_moving("cam1") is False

    def test_zero_move_is_not_moving(self):
        port = FakeCameraPort()
        port.move("cam1", 0, 0)
        assert port.is_moving("cam1") is False

    def test_multiple_cameras_isolated(self):
        port = FakeCameraPort()
        port.recall_preset("cam1", 3)
        port.recall_preset("cam2", 9)
        assert port.current_preset("cam1") == 3
        assert port.current_preset("cam2") == 9

    def test_calls_log_order(self):
        port = FakeCameraPort()
        port.power_on("cam1")
        port.recall_preset("cam1", 5)
        port.stop_move("cam1")
        assert port.calls == [
            "power_on:cam1",
            "recall_preset:cam1:5",
            "stop_move:cam1",
        ]

    def test_known_cameras_role_in_status(self):
        port = FakeCameraPort(known_cameras={"cam1": "main", "cam2": "comments"})
        assert port.get_status("cam1").role == "main"
        assert port.get_status("cam2").role == "comments"

    def test_unknown_camera_auto_registered(self):
        port = FakeCameraPort()
        status = port.get_status("cam99")
        assert status.camera_id == "cam99"
        assert status.adapter_type == "fake"


# ── ViscaCameraAdapter-specific tests ─────────────────────────────────────────

class TestViscaCameraAdapterDelegation:
    """ViscaCameraAdapter must construct correct VISCA bytes and use the right camera config."""

    def _adapter_with_confirmed_capture(self):
        adapter, mgr = _make_visca_adapter()
        calls = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True
        return adapter, mgr, calls

    def test_recall_preset_sends_correct_bytes_cam1(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {5: "04"})
        adapter, _, calls = self._adapter_with_confirmed_capture()
        adapter.recall_preset("cam1", 5)
        assert calls == [("10.0.0.1", "81", "01043f0204ff")]

    def test_recall_preset_cam2_uses_index_2(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {3: "02"})
        adapter, _, calls = self._adapter_with_confirmed_capture()
        adapter.recall_preset("cam2", 3)
        assert calls == [("10.0.0.2", "82", "01043f0202ff")]

    def test_save_preset_sends_correct_bytes(self, monkeypatch):
        import adapters.visca_camera_adapter as mod
        monkeypatch.setattr(mod, "PRESET_MAP", {2: "01"})
        adapter, _, calls = self._adapter_with_confirmed_capture()
        adapter.save_preset("cam1", 2)
        assert calls == [("10.0.0.1", "81", "01043f0101ff")]

    def test_move_enqueues_correct_payload(self):
        adapter, mgr, _ = self._adapter_with_confirmed_capture()
        adapter.move("cam1", 10, -5)
        worker = mgr.workers["10.0.0.1"]
        assert worker.sent
        payload = worker.sent[0].payload.hex().upper()
        # pan_dir=right(02), pan_abs=10; tilt_dir=down(02), tilt_abs=5
        assert payload == "810106010A050202FF"

    def test_stop_move_uses_priority_queue(self):
        adapter, mgr, _ = self._adapter_with_confirmed_capture()
        adapter.stop_move("cam1")
        worker = mgr.workers["10.0.0.1"]
        assert worker.sent == []
        assert worker.priority[0].payload.hex().upper() == "8101060100000303FF"

    def test_zoom_enqueues_correct_payload(self):
        adapter, mgr, _ = self._adapter_with_confirmed_capture()
        adapter.zoom("cam2", 3)
        worker = mgr.workers["10.0.0.2"]
        assert worker.sent[0].payload.hex().upper() == "8201040723FF"

    def test_power_on_uses_cam1_ip(self):
        adapter, _, calls = self._adapter_with_confirmed_capture()
        adapter.power_on("cam1")
        assert calls[0][0] == "10.0.0.1"

    def test_standby_uses_cam2_ip(self):
        adapter, _, calls = self._adapter_with_confirmed_capture()
        adapter.standby("cam2")
        assert calls[0][0] == "10.0.0.2"

    def test_home_uses_priority_queue(self):
        adapter, mgr, _ = self._adapter_with_confirmed_capture()
        adapter.home("cam1")
        worker = mgr.workers["10.0.0.1"]
        assert worker.sent == []
        assert worker.priority[0].payload.hex().upper() == "81010604FF"

    def test_failed_recall_sets_ok_false(self):
        adapter, _ = _make_visca_adapter(default_ok=False)
        result = adapter.recall_preset("cam1", 5)
        assert result.ok is False
        assert result.error_code == "CAMERA_ERROR"

    def test_failed_result_has_non_empty_message(self):
        adapter, _ = _make_visca_adapter(default_ok=False)
        result = adapter.power_on("cam1")
        assert result.message

    def test_unknown_camera_id_raises(self):
        adapter, _ = _make_visca_adapter()
        with pytest.raises(ValueError, match="unknown camera_id"):
            adapter.recall_preset("cam99", 1)

    def test_status_has_correct_role_cam1(self):
        adapter, _ = _make_visca_adapter()
        status = adapter.get_status("cam1")
        assert status.role == "main"
        assert status.adapter_type == "visca"

    def test_status_has_correct_role_cam2(self):
        adapter, _ = _make_visca_adapter()
        status = adapter.get_status("cam2")
        assert status.role == "comments"


# ── Focus / Exposure / Backlight / Zoom contract tests ────────────────────────

class TestCameraPortFocusExposureContract:
    """focus_auto / focus_manual / one_push_af / brightness_up / brightness_down
    / backlight_toggle / zoom_absolute must be available on both adapters and
    return a successful CommandResult with the correct command name.
    Issue: #739
    """

    @pytest.fixture(params=["fake", "visca"])
    def port_cam(self, request):
        if request.param == "fake":
            return FakeCameraPort(), "cam1"
        adapter, _ = _make_visca_adapter()
        return adapter, "cam1"

    def test_focus_auto_ok(self, port_cam):
        port, cam_id = port_cam
        result = port.focus_auto(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "focus_auto"

    def test_focus_manual_ok(self, port_cam):
        port, cam_id = port_cam
        result = port.focus_manual(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "focus_manual"

    def test_one_push_af_ok(self, port_cam):
        port, cam_id = port_cam
        result = port.one_push_af(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "one_push_af"

    def test_brightness_up_ok(self, port_cam):
        port, cam_id = port_cam
        result = port.brightness_up(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "brightness_up"

    def test_brightness_down_ok(self, port_cam):
        port, cam_id = port_cam
        result = port.brightness_down(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "brightness_down"

    def test_backlight_toggle_ok(self, port_cam):
        port, cam_id = port_cam
        result = port.backlight_toggle(cam_id)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "backlight_toggle"

    def test_zoom_absolute_ok(self, port_cam):
        port, cam_id = port_cam
        result = port.zoom_absolute(cam_id, 50)
        assert isinstance(result, CommandResult)
        assert result.ok is True
        assert result.command == "zoom_absolute"

    def test_fake_focus_auto_logged(self):
        port = FakeCameraPort()
        port.focus_auto("cam1")
        assert "focus_auto:cam1" in port.calls

    def test_fake_backlight_toggle_flips_state(self):
        port = FakeCameraPort()
        port.backlight_toggle("cam1")
        assert port._backlight_on["cam1"] is True
        port.backlight_toggle("cam1")
        assert port._backlight_on["cam1"] is False

    def test_visca_adapter_focus_auto_sends_correct_bytes(self):
        adapter, _ = _make_visca_adapter()
        calls = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True
        adapter.focus_auto("cam1")
        assert calls == [("10.0.0.1", "81", "01043802FF")]

    def test_visca_adapter_backlight_toggle_sends_enable_then_disable(self):
        adapter, _ = _make_visca_adapter()
        calls = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True
        adapter.backlight_toggle("cam1")  # first → enable
        adapter.backlight_toggle("cam1")  # second → disable
        assert calls[0][2] == "01043302FF"
        assert calls[1][2] == "01043303FF"

    def test_visca_adapter_zoom_absolute_sends_correct_bytes(self):
        adapter, _ = _make_visca_adapter()
        calls = []
        adapter._send_confirmed = lambda ip, cam_id, cmd: calls.append((ip, cam_id, cmd)) or True
        adapter.zoom_absolute("cam2", 75)
        assert calls[0][0] == "10.0.0.2"
        assert calls[0][2].startswith("010447")
