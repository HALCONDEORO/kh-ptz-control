#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_gui_user_service_contract.py — Session-owned GUI contract (#885)
#
# #885 replaces the manual X11 repair with a GUI that runs inside the desktop
# session. The failure modes it must prevent are severe — two competing GUIs
# fighting over the same cameras, or no GUI at all — and none of them can be
# reproduced without a Pi. These are static assertions over the shipped units,
# launcher and installer logic, so they run everywhere.

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
USER_UNIT = REPO_ROOT / "runtime" / "systemd" / "user" / "khptz-gui.service"
SYSTEM_UNIT = REPO_ROOT / "runtime" / "systemd" / "khptz-control.service"
HELPER = REPO_ROOT / "runtime" / "khptz-gui-session.sh"
AUTOSTART = REPO_ROOT / "runtime" / "khptz-gui.desktop"
INSTALLER = REPO_ROOT / "runtime" / "installer" / "install.sh"
ROLLBACK = REPO_ROOT / "runtime" / "installer" / "rollback.sh"
BOOTSTRAP = REPO_ROOT / "install_khptz_rpi.sh"


def _sections(text: str) -> dict[str, list[tuple[str, str]]]:
    """Parse an ini-style unit into {section: [(key, value), ...]}."""
    out: dict[str, list[tuple[str, str]]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            out.setdefault(section, [])
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            out.setdefault(section, []).append((key.strip(), value.strip()))
    return out


@pytest.fixture(scope="module")
def user_unit() -> dict[str, list[tuple[str, str]]]:
    return _sections(USER_UNIT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def system_unit() -> dict[str, list[tuple[str, str]]]:
    return _sections(SYSTEM_UNIT.read_text(encoding="utf-8"))


def _values(unit, section, key) -> list[str]:
    return [v for k, v in unit.get(section, []) if k == key]


class TestArtifactsExist:
    @pytest.mark.parametrize("path", [USER_UNIT, HELPER, AUTOSTART])
    def test_shipped(self, path):
        assert path.is_file(), f"{path} is missing"


class TestRestartLimitsAreInTheUnitSection:
    """StartLimitIntervalSec/StartLimitBurst are [Unit] directives (systemd >=
    229). In [Service] systemd ignores them, so the burst cap silently does not
    apply and a failing GUI restarts forever — the loop #885 must bound and the
    bootstrap's NRestarts check assumes exists."""

    @pytest.mark.parametrize("key", ["StartLimitIntervalSec", "StartLimitBurst"])
    def test_system_unit_declares_them_under_unit(self, system_unit, key):
        assert _values(system_unit, "Unit", key), f"{key} must be in [Unit]"
        assert not _values(system_unit, "Service", key), (
            f"{key} in [Service] is ignored by systemd — move it to [Unit]"
        )

    @pytest.mark.parametrize("key", ["StartLimitIntervalSec", "StartLimitBurst"])
    def test_user_unit_declares_them_under_unit(self, user_unit, key):
        assert _values(user_unit, "Unit", key), f"{key} must be in [Unit]"
        assert not _values(user_unit, "Service", key)

    def test_both_units_restart_on_failure_only(self, user_unit, system_unit):
        for unit in (user_unit, system_unit):
            assert _values(unit, "Service", "Restart") == ["on-failure"]


class TestUserUnitInheritsTheSession:
    """The entire point of #885: the GUI must take the session's own display
    environment rather than having one grafted onto it."""

    @pytest.mark.parametrize("var", ["DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR"])
    def test_does_not_hardcode_session_environment(self, user_unit, var):
        hardcoded = [v for v in _values(user_unit, "Service", "Environment")
                     if v.startswith(f"{var}=")]
        assert not hardcoded, (
            f"{var} is hardcoded in the user unit; it must come from the session"
        )

    def test_does_not_run_as_a_fixed_user(self, user_unit):
        """A user unit runs as whoever owns the session — pinning User= would
        reintroduce exactly the identity split #885 removes."""
        assert not _values(user_unit, "Service", "User")
        assert not _values(user_unit, "Service", "Group")

    def test_keeps_the_utf8_environment(self, user_unit):
        env = _values(user_unit, "Service", "Environment")
        for expected in ("LANG=C.UTF-8", "PYTHONUTF8=1", "PYTHONIOENCODING=utf-8"):
            assert expected in env, f"{expected} missing (#884 regression risk)"

    def test_is_gated_on_provisioning(self, user_unit):
        assert "/etc/khptz/.provisioned" in _values(user_unit, "Unit", "ConditionPathExists")

    def test_does_not_sandbox_away_its_own_data_paths(self, user_unit):
        """ProtectSystem=strict would block the writes to /var/lib/khptz and
        /var/log/khptz this unit must make."""
        assert not _values(user_unit, "Service", "ProtectSystem")

    def test_is_not_enabled_into_a_target_lxde_may_never_reach(self, user_unit):
        """Bullseye runs LXDE, which does not reliably activate
        graphical-session.target; default.target would fire for SSH logins too.
        The unit is started explicitly by the XDG autostart entry instead."""
        assert "Install" not in user_unit or not _values(user_unit, "Install", "WantedBy")


class TestLauncherImportsTheEnvironment:
    @pytest.fixture(scope="class")
    def helper_text(self) -> str:
        return HELPER.read_text(encoding="utf-8")

    def test_imports_the_session_environment(self, helper_text):
        assert "import-environment" in helper_text
        for var in ("DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS"):
            assert var in helper_text, f"{var} is not handed to the user manager"

    def test_refuses_to_start_without_a_display(self, helper_text):
        """Guards the SSH-login case: no display means no GUI, not a crash loop."""
        assert 'DISPLAY:-' in helper_text

    def test_starts_the_unit_rather_than_the_app_directly(self, helper_text):
        """Launching main.py straight from autostart would lose supervision,
        restart bounds and the single-instance guarantee."""
        assert "systemctl --user start" in helper_text
        assert "main.py" not in helper_text

    def test_does_not_block_the_desktop_session(self, helper_text):
        assert "--no-block" in helper_text

    def test_autostart_points_at_the_helper(self):
        desktop = AUTOSTART.read_text(encoding="utf-8")
        assert "Exec=/usr/local/libexec/khptz-gui-session" in desktop
        assert "Type=Application" in desktop


class TestExactlyOneLauncher:
    """Two enabled launchers would open two full-screen GUIs driving the same
    cameras — the worst outcome of getting this wrong."""

    @pytest.fixture(scope="class")
    def installer_text(self) -> str:
        return INSTALLER.read_text(encoding="utf-8")

    def test_user_mode_disables_the_system_service(self, installer_text):
        assert re.search(r'GUI_MODE.*==.*"user"', installer_text)
        assert re.search(r'systemctl disable "\$\{SERVICE_NAME\}"', installer_text)

    def test_system_mode_removes_the_session_launcher(self, installer_text):
        """Switching back must strip the user unit, helper and autostart."""
        assert "GUI_UNIT_TARGET" in installer_text
        assert "GUI_HELPER_TARGET" in installer_text
        assert re.search(r"rm -f -- \"\$\{_stale\}\"", installer_text)

    def test_gui_mode_is_validated(self, installer_text):
        assert "Invalid --gui-mode" in installer_text

    def test_gui_mode_is_recorded_for_rollback(self, installer_text):
        assert "KHPTZ_GUI_MODE=" in installer_text

    def test_rollback_preserves_the_recorded_mode(self):
        """Without this a rollback silently reverts to the system service and
        leaves the session launcher behind — two launchers again."""
        text = ROLLBACK.read_text(encoding="utf-8")
        assert "KHPTZ_GUI_MODE" in text
        assert "--gui-mode" in text


class TestBootstrapIsModeAware:
    @pytest.fixture(scope="class")
    def bootstrap_text(self) -> str:
        return BOOTSTRAP.read_text(encoding="utf-8")

    def test_passes_the_mode_through(self, bootstrap_text):
        assert "--gui-mode" in bootstrap_text
        assert "_validate_gui_mode" in bootstrap_text

    def test_flags_a_system_service_left_enabled_in_user_mode(self, bootstrap_text):
        """That combination is precisely the two-GUI failure; it must be fatal,
        not a warning."""
        assert "STILL enabled" in bootstrap_text

    def test_does_not_check_user_units_from_the_installer(self, bootstrap_text):
        """The desktop user's manager does not exist until they log in, so
        `systemctl --user` from a root install would be meaningless.

        Only *active* lines count — the script explains in a comment why it
        deliberately avoids this call.
        """
        active = [
            line for line in bootstrap_text.splitlines()
            if "systemctl --user" in line and not line.lstrip().startswith("#")
        ]
        assert not active, f"bootstrap invokes a user manager it cannot reach: {active}"
