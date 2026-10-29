#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_provision_gui_mode.py — provisioning respects the GUI mode (#885)
#
# The bug: runtime/provision.py runs as root from the wizard's provisioning
# channel on EVERY install, and knew nothing about HALLPTZ_GUI_MODE. On a
# --gui-mode user appliance, completing the wizard therefore
#
#   1. re-enabled hallptz-control (a second launcher armed for the next boot),
#   2. RESTARTED it — putting a second full-screen GUI on the cameras
#      immediately, while the operator was still in the wizard, and
#   3. reset /var/lib|log|backups/hallptz to 0750, undoing the group-writable
#      permissions the session GUI needs to save presets at all.
#
# The shell half of the same chain (repair_rpi_runtime.sh) was fixed first;
# this is its Python counterpart. Both read the mode through a single reader.

from __future__ import annotations

from pathlib import Path

import pytest

from runtime import install_state, provision


class _Resolver:
    """Minimal stand-in for RuntimePathResolver with a redirectable config dir."""

    def __init__(self, root: Path):
        self.config_dir = root / "etc"
        self.data_dir = root / "var-lib"
        self.log_dir = root / "var-log"
        self.backup_dir = root / "var-backups"
        for d in (self.config_dir, self.data_dir, self.log_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)

    def write_mode(self, mode: str | None) -> None:
        state = self.config_dir / "install-state.env"
        if mode is None:
            state.unlink(missing_ok=True)
            return
        state.write_text(f'HALLPTZ_GUI_MODE="{mode}"\n', encoding="utf-8")


@pytest.fixture
def resolver(tmp_path: Path) -> _Resolver:
    return _Resolver(tmp_path)


def _flat(commands: list[list[str]]) -> str:
    return " | ".join(" ".join(c) for c in commands)


class TestServiceActivation:
    def test_system_mode_still_enables_the_service(self, resolver):
        resolver.write_mode("system")
        cmds = provision.plan_system_commands(resolver)
        assert ["systemctl", "enable", provision.SERVICE_NAME] in cmds

    def test_user_mode_does_not_enable_the_service(self, resolver):
        """install.sh deliberately disabled it; re-enabling arms a second GUI."""
        resolver.write_mode("user")
        cmds = provision.plan_system_commands(resolver)
        assert ["systemctl", "enable", provision.SERVICE_NAME] not in cmds, _flat(cmds)

    def test_user_mode_still_reloads_systemd(self, resolver):
        """Skipping the enable must not skip the reload the units need."""
        resolver.write_mode("user")
        cmds = provision.plan_system_commands(resolver)
        assert ["systemctl", "daemon-reload"] in cmds

    def test_missing_state_behaves_as_system(self, resolver):
        """Installs predating the flag were all system mode."""
        resolver.write_mode(None)
        cmds = provision.plan_system_commands(resolver)
        assert ["systemctl", "enable", provision.SERVICE_NAME] in cmds


class TestRuntimeDirectoryModes:
    """Provisioning must not undo what the installer set for the mode."""

    def _modes(self, resolver) -> list[str]:
        return [
            c[c.index("-m") + 1]
            for c in provision.plan_system_commands(resolver)
            if c[:1] == ["install"] and "-m" in c
        ]

    def test_system_mode_keeps_runtime_dirs_private(self, resolver):
        resolver.write_mode("system")
        assert "0750" in self._modes(resolver)
        assert "2770" not in self._modes(resolver)

    def test_user_mode_keeps_runtime_dirs_group_writable(self, resolver):
        """0750 here would leave the GUI unable to write presets or logs."""
        resolver.write_mode("user")
        modes = self._modes(resolver)
        assert "2770" in modes
        assert "0750" not in modes

    def test_config_dir_mode_is_unchanged_by_gui_mode(self, resolver):
        """Config stays admin-write / service-read in both modes; only the
        runtime data directories are shared."""
        for mode in ("system", "user"):
            resolver.write_mode(mode)
            assert "2751" in self._modes(resolver)


class TestRestartIsSuppressedForASessionOwnedGui:
    def test_system_mode_restarts(self, monkeypatch, resolver):
        monkeypatch.setattr(install_state, "gui_is_session_owned", lambda *a, **k: False)
        calls: list[list[str]] = []
        provision._restart_control_service(runner=calls.append)
        assert calls == [["systemctl", "restart", provision.SERVICE_NAME]]

    def test_user_mode_does_not_restart(self, monkeypatch, resolver):
        """A restart would open a second GUI immediately, mid-wizard."""
        monkeypatch.setattr(install_state, "gui_is_session_owned", lambda *a, **k: True)
        calls: list[list[str]] = []
        provision._restart_control_service(runner=calls.append)
        assert calls == []

    def test_restart_failure_still_never_raises(self, monkeypatch):
        monkeypatch.setattr(install_state, "gui_is_session_owned", lambda *a, **k: False)

        def _boom(cmd):
            raise OSError("systemd unavailable")

        provision._restart_control_service(runner=_boom)  # must not raise


class TestSharedPythonReader:
    """Mirrors scripts/lib/install_state.sh; the two must not drift."""

    def test_reads_user(self, resolver):
        resolver.write_mode("user")
        assert install_state.gui_mode(resolver) == "user"

    def test_reads_system(self, resolver):
        resolver.write_mode("system")
        assert install_state.gui_mode(resolver) == "system"

    def test_unknown_value_falls_back_to_system(self, resolver):
        resolver.write_mode("banana")
        assert install_state.gui_mode(resolver) == "system"

    def test_missing_file_falls_back_to_system(self, resolver):
        resolver.write_mode(None)
        assert install_state.gui_mode(resolver) == "system"

    def test_unquoted_value(self, resolver):
        (resolver.config_dir / "install-state.env").write_text(
            "HALLPTZ_GUI_MODE=user\n", encoding="utf-8"
        )
        assert install_state.gui_mode(resolver) == "user"

    def test_state_file_is_parsed_not_sourced(self, resolver):
        """A malformed entry must not be able to execute anything."""
        (resolver.config_dir / "install-state.env").write_text(
            'HALLPTZ_GUI_MODE="user"; touch /tmp/pwned\n', encoding="utf-8"
        )
        # The value is taken literally, so it is not a recognised mode.
        assert install_state.gui_mode(resolver) == "system"

    def test_last_occurrence_wins(self, resolver):
        (resolver.config_dir / "install-state.env").write_text(
            'HALLPTZ_GUI_MODE="system"\nHALLPTZ_GUI_MODE="user"\n', encoding="utf-8"
        )
        assert install_state.gui_mode(resolver) == "user"
