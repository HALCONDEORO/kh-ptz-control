#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_sim_worker.py — the simulation façade had no coverage
#
# simulation/sim_worker.py is what demo and simulation profiles call before the
# camera worker tries to connect. Two things must hold:
#
#   - a partial start is reported honestly. If only one mock server binds, the
#     caller has to learn that; silently returning success leaves the operator
#     staring at a camera that never answers, in the one mode where there is no
#     hardware to blame.
#   - a missing simulator never takes the app down. hardware_simulator is not
#     shipped on every install, and an ImportError escaping here would abort
#     startup instead of degrading to "no simulation".

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from simulation import sim_worker


class _FakeCamera:
    def __init__(self, name: str):
        self.name = name


class _FakeServer:
    """Records what it was constructed with and whether start() succeeded."""

    instances: list = []

    def __init__(self, ip, camera, ok=True):
        self.ip = ip
        self.camera = camera
        self._ok = ok
        _FakeServer.instances.append(self)

    def start(self) -> bool:
        return self._ok


@pytest.fixture
def fake_simulator(monkeypatch):
    """Install a stand-in adapters.hardware_simulator for the lazy import."""
    _FakeServer.instances = []
    module = types.ModuleType("adapters.hardware_simulator")
    module.SimCamera = _FakeCamera
    module.ViscaServer = _FakeServer
    module.active_cam1 = None
    module.active_cam2 = None
    monkeypatch.setitem(sys.modules, "adapters.hardware_simulator", module)
    # `import adapters.hardware_simulator as _sim` binds through the parent
    # package attribute, so replacing the sys.modules entry alone is not enough
    # once the real module has been imported by another test.
    import adapters
    monkeypatch.setattr(adapters, "hardware_simulator", module, raising=False)
    return module


class TestStartSimulation:
    def test_both_servers_started(self, fake_simulator):
        assert sim_worker.start_simulation("10.0.0.1", "10.0.0.2") == (True, True)

    def test_servers_bind_the_requested_addresses(self, fake_simulator):
        sim_worker.start_simulation("10.0.0.1", "10.0.0.2")
        assert [s.ip for s in _FakeServer.instances] == ["10.0.0.1", "10.0.0.2"]

    def test_cameras_keep_their_production_roles(self, fake_simulator):
        """The names appear in the sim debug panel and in the logs — swapping
        them makes every simulated session read backwards."""
        sim_worker.start_simulation("10.0.0.1", "10.0.0.2")
        assert [s.camera.name for s in _FakeServer.instances] == [
            "CAM1-Platform", "CAM2-Comments",
        ]

    def test_started_cameras_are_published_for_the_debug_panel(self, fake_simulator):
        sim_worker.start_simulation("10.0.0.1", "10.0.0.2")
        assert fake_simulator.active_cam1.name == "CAM1-Platform"
        assert fake_simulator.active_cam2.name == "CAM2-Comments"

    def test_a_failed_server_is_reported(self, fake_simulator, monkeypatch):
        monkeypatch.setattr(
            fake_simulator, "ViscaServer",
            lambda ip, cam: _FakeServer(ip, cam, ok=(ip == "10.0.0.1")),
        )
        assert sim_worker.start_simulation("10.0.0.1", "10.0.0.2") == (True, False)

    def test_a_failed_server_is_not_published_as_active(self, fake_simulator, monkeypatch):
        """Publishing a camera whose server never bound would make the debug
        panel report state for a link that does not exist."""
        monkeypatch.setattr(
            fake_simulator, "ViscaServer",
            lambda ip, cam: _FakeServer(ip, cam, ok=(ip == "10.0.0.1")),
        )
        sim_worker.start_simulation("10.0.0.1", "10.0.0.2")
        assert fake_simulator.active_cam1 is not None
        assert fake_simulator.active_cam2 is None

    def test_a_partial_start_is_logged(self, fake_simulator, monkeypatch, caplog):
        monkeypatch.setattr(
            fake_simulator, "ViscaServer",
            lambda ip, cam: _FakeServer(ip, cam, ok=False),
        )
        with caplog.at_level("WARNING"):
            sim_worker.start_simulation("10.0.0.1", "10.0.0.2")
        assert any("SimVISCA" in r.message for r in caplog.records)

    def test_a_full_start_logs_no_warning(self, fake_simulator, caplog):
        with caplog.at_level("WARNING"):
            sim_worker.start_simulation("10.0.0.1", "10.0.0.2")
        assert not [r for r in caplog.records if r.levelname == "WARNING"]

    def test_missing_simulator_does_not_propagate(self, monkeypatch):
        """Setting the entry to None makes the import raise, exactly as it does
        on an install that ships without the simulator."""
        monkeypatch.setitem(sys.modules, "adapters.hardware_simulator", None)
        assert sim_worker.start_simulation("10.0.0.1", "10.0.0.2") == (False, False)


class TestIsSimulationActive:
    def test_true_when_the_ip_backup_exists(self, monkeypatch, tmp_path: Path):
        backup = tmp_path / "sim_ip_backup.json"
        backup.write_text("{}", encoding="utf-8")
        import adapters.sim_mode as sim_mode
        monkeypatch.setattr(sim_mode, "BACKUP", backup)
        assert sim_worker.is_simulation_active() is True

    def test_false_without_the_ip_backup(self, monkeypatch, tmp_path: Path):
        import adapters.sim_mode as sim_mode
        monkeypatch.setattr(sim_mode, "BACKUP", tmp_path / "absent.json")
        assert sim_worker.is_simulation_active() is False
