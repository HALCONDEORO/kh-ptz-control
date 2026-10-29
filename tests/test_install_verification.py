#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application.install_verification — the wizard's post-provision check."""

from __future__ import annotations

import pytest

from application.install_verification import _launcher_checks, verify_provisioned
from runtime.path_resolver import RuntimePathResolver


@pytest.fixture
def resolver(tmp_path, monkeypatch):
    monkeypatch.setenv("KHPTZ_CONFIG_DIR", str(tmp_path / "etc"))
    monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "data"))
    r = RuntimePathResolver()
    r.config_dir.mkdir(parents=True, exist_ok=True)
    return r


def test_passes_when_marker_and_config_present(resolver):
    (resolver.config_dir / "config.yaml").write_text("x", encoding="utf-8")
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
    verdict = verify_provisioned(resolver)
    assert verdict.ok is True
    assert "verified" in verdict.summary().lower()


def test_fails_when_marker_missing(resolver):
    (resolver.config_dir / "config.yaml").write_text("x", encoding="utf-8")
    verdict = verify_provisioned(resolver)
    assert verdict.ok is False
    assert "Provisioned marker" in verdict.summary()


def test_fails_when_config_missing(resolver):
    resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
    verdict = verify_provisioned(resolver)
    assert verdict.ok is False
    assert "Configuration file" in verdict.summary()


class TestLauncherChecksFollowTheInstalledGuiMode:
    """The final wizard screen must verify the launcher this install has (#885).

    scripts/repair_rpi_runtime.sh deliberately skips the entire display-ready
    chain under --gui-mode user ("the session owns its own display"), so
    /run/khptz/display-ready is never written there. Demanding it anyway made
    the Done page report "Setup finished but verification failed" on every
    healthy session-owned install — the wizard contradicting itself at the last
    step of a successful setup.
    """

    @staticmethod
    def _labels(monkeypatch, *, session_owned: bool) -> list[str]:
        import runtime.install_state as install_state

        monkeypatch.setattr(
            install_state, "gui_is_session_owned", lambda *a, **k: session_owned
        )
        return [label for label, _ in _launcher_checks()]

    def test_system_mode_verifies_the_display_ready_chain(self, monkeypatch):
        labels = self._labels(monkeypatch, session_owned=False)
        assert "Desktop display handoff" in labels
        assert "Display-ready path unit" in labels
        assert "KHPTZ service unit" in labels

    def test_user_mode_does_not_demand_the_display_handoff(self, monkeypatch):
        labels = self._labels(monkeypatch, session_owned=True)
        assert "Desktop display handoff" not in labels
        assert "Display-ready path unit" not in labels

    def test_user_mode_verifies_the_session_launcher_instead(self, monkeypatch):
        """Skipping a check is only correct if the real launcher is checked."""
        labels = self._labels(monkeypatch, session_owned=True)
        assert "Session GUI unit" in labels
        assert "Session GUI launcher" in labels
        assert "Session GUI autostart" in labels

    def test_user_mode_autostart_check_reads_the_wizard_users_own_home(
        self, monkeypatch, tmp_path
    ):
        """The autostart entry is what starts the GUI at login, and this
        process runs as the desktop user — so its own home is the right place
        to look for it."""
        import runtime.install_state as install_state
        from application import install_verification as iv

        monkeypatch.setattr(install_state, "gui_is_session_owned", lambda *a, **k: True)
        monkeypatch.setattr(iv.Path, "home", staticmethod(lambda: tmp_path))
        assert dict(_launcher_checks())["Session GUI autostart"] is False

        entry = tmp_path / ".config" / "autostart" / "khptz-gui.desktop"
        entry.parent.mkdir(parents=True)
        entry.write_text("[Desktop Entry]\n", encoding="utf-8")
        assert dict(_launcher_checks())["Session GUI autostart"] is True

    def test_an_unreadable_gui_mode_falls_back_to_system(self, monkeypatch):
        import runtime.install_state as install_state

        def _boom(*_a, **_k):
            raise OSError("no install state")

        monkeypatch.setattr(install_state, "gui_is_session_owned", _boom)
        labels = [label for label, _ in _launcher_checks()]
        assert "Desktop display handoff" in labels

    def test_non_product_installs_run_no_launcher_checks(self, resolver):
        """Dev/test installs use overridden paths and ship no systemd wiring."""
        (resolver.config_dir / "config.yaml").write_text("x", encoding="utf-8")
        resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")
        labels = [label for label, _ in verify_provisioned(resolver).checks]
        assert labels == ["Provisioned marker", "Configuration file"]
