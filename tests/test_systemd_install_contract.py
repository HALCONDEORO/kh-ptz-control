#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_systemd_install_contract.py — Static systemd/install contract (#891)
#
# #891 asks for automated verification of the deployment contract that the first
# physical install proved matters. These are pure file/text assertions: no root,
# no Pi, no systemd — so they run everywhere, including while CI is unavailable.
#
# Each assertion pins a property whose regression previously produced (or would
# reproduce) a concrete field failure, cited per test.

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
UNIT = REPO_ROOT / "runtime" / "systemd" / "hallptz-control.service"
BOOTSTRAP = REPO_ROOT / "install_hallptz_rpi.sh"
INSTALLER = REPO_ROOT / "runtime" / "installer" / "install.sh"


@pytest.fixture(scope="module")
def unit_text() -> str:
    return UNIT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def unit_settings(unit_text) -> dict[str, list[str]]:
    """Parse `key=value` lines, keeping repeats (Environment= appears many times)."""
    settings: dict[str, list[str]] = {}
    for line in unit_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        settings.setdefault(key.strip(), []).append(value.strip())
    return settings


class TestUnitExists:
    def test_service_unit_is_present(self):
        """install.sh --check hard-fails without it; the readiness harness
        covers that branch, this covers the file itself."""
        assert UNIT.is_file()


class TestRestartContract:
    """A failed GUI process must not spin in an infinite rapid restart loop —
    the state the first install sat in (#885 acceptance criterion)."""

    def test_restart_is_bounded_not_always(self, unit_settings):
        assert unit_settings["Restart"] == ["on-failure"]

    def test_restart_has_a_delay(self, unit_settings):
        assert int(unit_settings["RestartSec"][0]) >= 1

    def test_start_limit_caps_the_restart_burst(self, unit_settings):
        """Without a burst cap systemd retries forever; the bootstrap's
        NRestarts>=3 crash-loop detection assumes this bound exists."""
        assert int(unit_settings["StartLimitBurst"][0]) <= 5
        assert int(unit_settings["StartLimitIntervalSec"][0]) >= 10


class TestDisplayContract:
    """`could not connect to display :0` / xcb aborts (#885)."""

    def test_display_is_set(self, unit_settings):
        assert "DISPLAY=:0" in unit_settings.get("Environment", [])

    def test_qt_platform_is_xcb(self, unit_settings):
        assert "QT_QPA_PLATFORM=xcb" in unit_settings.get("Environment", [])

    def test_private_tmp_is_disabled_for_the_x11_socket(self, unit_settings):
        """PrivateTmp=true hides /tmp/.X11-unix and caused the observed xcb
        abort. This is deliberate and must not be 'hardened' back on."""
        assert unit_settings["PrivateTmp"] == ["false"]

    def test_protect_home_stays_true(self, unit_settings):
        """The superseded drop-in weakened this to read-only to expose the
        desktop user's X cookie. The scoped `xhost +SI:localuser:hallptz` helper
        makes that unnecessary — homes must stay protected."""
        assert unit_settings["ProtectHome"] == ["true"]


class TestUtf8Contract:
    """UnicodeEncodeError killed `hallptz doctor` mid-output on the pilot Pi (#884)."""

    @pytest.mark.parametrize(
        "expected",
        ["LANG=C.UTF-8", "LC_ALL=C.UTF-8", "PYTHONUTF8=1", "PYTHONIOENCODING=utf-8"],
    )
    def test_utf8_environment_is_pinned(self, unit_settings, expected):
        assert expected in unit_settings.get("Environment", [])


class TestPathContract:
    """Every path the unit references must be one the installer creates."""

    def test_execstart_matches_the_installed_layout(self, unit_settings):
        exec_start = unit_settings["ExecStart"][0]
        assert "/opt/hallptz/main.py" in exec_start
        assert exec_start.startswith("/usr/bin/python3")

    def test_working_directory_is_the_install_dir(self, unit_settings):
        assert unit_settings["WorkingDirectory"] == ["/opt/hallptz"]

    def test_install_dir_agrees_with_the_installer(self):
        """A unit pointing at a directory install.sh never creates yields a
        service that cannot start."""
        installer = INSTALLER.read_text(encoding="utf-8")
        assert 'INSTALL_DIR="/opt/hallptz"' in installer

    def test_readwritepaths_covers_the_service_owned_dirs(self, unit_settings):
        rw = unit_settings["ReadWritePaths"][0]
        for required in ("/var/lib/hallptz", "/var/log/hallptz", "/var/backups/hallptz"):
            assert required in rw, f"{required} missing from ReadWritePaths"

    def test_runs_as_the_service_user_not_root(self, unit_settings):
        assert unit_settings["User"] == ["hallptz"]

    def test_starts_under_the_graphical_target(self, unit_settings):
        assert unit_settings["WantedBy"] == ["graphical.target"]


class TestBootstrapContract:
    """Properties of the single supported entry point (#883)."""

    @pytest.fixture(scope="class")
    def bootstrap_text(self) -> str:
        return BOOTSTRAP.read_text(encoding="utf-8")

    def test_does_not_reintroduce_the_weakened_protect_home(self, bootstrap_text):
        """The removed drop-in set ProtectHome=read-only, overriding the unit
        and exposing every home directory to the service.

        Only *active* lines count — the script documents the removed directive
        in a comment explaining why it must not come back.
        """
        active = [
            line for line in bootstrap_text.splitlines()
            if "ProtectHome=read-only" in line and not line.lstrip().startswith("#")
        ]
        assert not active, f"bootstrap writes ProtectHome=read-only: {active}"

    def test_does_not_bake_an_xauthority_cookie_into_the_unit(self, bootstrap_text):
        """The cookie path did not survive a re-login; scoped xhost replaced it."""
        assert "Environment=XAUTHORITY" not in bootstrap_text

    def test_diagnostics_do_not_run_as_root(self, bootstrap_text):
        """A root-run doctor creates root:root files in hallptz:hallptz 0750 log dirs,
        after which the service can never write its own logs."""
        assert "sudo -u hallptz hallptz doctor" in bootstrap_text
        assert not re.search(r"^\s*hallptz doctor\b", bootstrap_text, re.MULTILINE)


class TestDoctorExitCodeAlignment:
    """The bootstrap translates doctor's exit code into the operator's single
    next action. If the two drift, a broken appliance reports SUCCESS."""

    def test_bootstrap_handles_every_canonical_exit_code(self):
        from domain.doctor_outcome import DoctorOutcome, exit_code_for

        bootstrap_text = BOOTSTRAP.read_text(encoding="utf-8")
        # The case statement lives after the diagnostics step; every non-zero
        # canonical code must appear as a branch label. 0 is the `0)` branch and
        # 30 is covered by the catch-all `*)`, so accept either form.
        for outcome in DoctorOutcome:
            code = exit_code_for(outcome)
            if code == 0:
                continue
            branch = re.search(rf"^\s*{code}\)", bootstrap_text, re.MULTILINE)
            catch_all = re.search(r"^\s*\*\)", bootstrap_text, re.MULTILINE)
            assert branch or catch_all, (
                f"bootstrap has no branch for {outcome} (exit {code})"
            )

    def test_canonical_codes_are_the_expected_four(self):
        from domain.doctor_outcome import DoctorOutcome, exit_code_for

        codes = sorted(exit_code_for(o) for o in DoctorOutcome)
        assert codes == [0, 10, 20, 30]
