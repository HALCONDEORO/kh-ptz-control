#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for application.provisioning_service — the headless wizard engine.

No Qt, no hardware, no root: paths are redirected to a temp dir and secrets are
isolated by monkeypatching secret_manager's module-level paths.
"""

from __future__ import annotations

import pytest

from application.provisioning_service import (
    CameraAnswer,
    ProvisioningAnswers,
    ProvisioningService,
)
from config.loader import load_config
from runtime import secret_manager
from runtime.path_resolver import RuntimePathResolver


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Point config/data dirs and secret files at a temp tree."""
    config_dir = tmp_path / "etc"
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("HALLPTZ_DATA_DIR", str(data_dir))
    monkeypatch.setattr(secret_manager, "_CONFIG_DIR", data_dir)
    monkeypatch.setattr(secret_manager, "_ENC_FILE", data_dir / "password.enc")
    return RuntimePathResolver()


def _ready_answers() -> ProvisioningAnswers:
    a = ProvisioningAnswers()
    a.entry_password = "operator-pw"
    a.admin_password = "admin-pw"
    return a


class TestToAppSettings:

    def test_defaults_produce_two_cameras(self):
        s = ProvisioningService().to_app_settings(ProvisioningAnswers())
        assert [c.role for c in s.cameras] == ["platform", "comments"]

    def test_blank_name_is_derived_from_role(self):
        a = ProvisioningAnswers(cameras=[
            CameraAnswer(id="p", role="platform", ip="172.16.1.11", visca_id="81"),
        ])
        s = ProvisioningService().to_app_settings(a)
        assert s.cameras[0].name == "Platform"

    def test_atem_toggle_sets_installed_and_feature(self):
        a = _ready_answers()
        a.atem_enabled = True
        s = ProvisioningService().to_app_settings(a)
        assert s.atem.installed is True and s.atem.enabled is True
        assert s.features.atem_enabled is True


class TestValidate:

    def test_default_answers_only_miss_passwords(self):
        issues = ProvisioningService().validate(ProvisioningAnswers())
        fields = {i.field_path for i in issues}
        assert fields == {"entry_password", "admin_password"}

    def test_ready_answers_have_no_issues(self):
        assert ProvisioningService().validate(_ready_answers()) == []

    def test_invalid_ip_is_reported(self):
        a = _ready_answers()
        a.cameras[0].ip = "999.1.1.1"
        issues = ProvisioningService().validate(a)
        assert any("ip" in i.field_path for i in issues)

    def test_duplicate_visca_is_reported(self):
        a = _ready_answers()
        a.cameras[1].visca_id = a.cameras[0].visca_id
        issues = ProvisioningService().validate(a)
        assert any("visca" in i.field_path.lower() for i in issues)

    def test_no_cameras_is_reported(self):
        a = _ready_answers()
        a.cameras = []
        issues = ProvisioningService().validate(a)
        assert any(i.field_path == "cameras" for i in issues)


class TestPlan:

    def test_plan_lists_core_artifacts(self, isolated):
        plan = ProvisioningService().plan(_ready_answers(), resolver=isolated)
        kinds = {a.kind for a in plan.artifacts}
        assert {"user", "config", "secret", "service", "marker"} <= kinds

    def test_plan_has_two_secrets(self, isolated):
        plan = ProvisioningService().plan(_ready_answers(), resolver=isolated)
        secrets = [a for a in plan.artifacts if a.kind == "secret"]
        assert len(secrets) == 2


class TestApplyFiles:

    def test_writes_loadable_config(self, isolated):
        ProvisioningService().apply_files(_ready_answers(), resolver=isolated)
        config = isolated.config_dir / "config.yaml"
        assert config.exists()
        loaded = load_config(config)
        assert [c.name for c in loaded.cameras] == ["Main Platform", "Comments Desk"]

    def test_writes_both_secrets_recoverable(self, isolated):
        ProvisioningService().apply_files(_ready_answers(), resolver=isolated)
        assert secret_manager.decrypt_secret(secret_manager.SECRET_ENTRY) == "operator-pw"
        assert secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN) == "admin-pw"

    def test_result_lists_three_written_files(self, isolated):
        result = ProvisioningService().apply_files(_ready_answers(), resolver=isolated)
        assert result.ok is True
        assert len(result.written) == 3

    def test_apply_is_idempotent(self, isolated):
        svc = ProvisioningService()
        svc.apply_files(_ready_answers(), resolver=isolated)
        svc.apply_files(_ready_answers(), resolver=isolated)
        # Second run must still leave a loadable config and recoverable secrets.
        load_config(isolated.config_dir / "config.yaml")
        assert secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN) == "admin-pw"


class TestRepairPrefill:
    """Repair mode reads an existing install back into editable answers."""

    def test_answers_from_settings_round_trip(self):
        svc = ProvisioningService()
        original = _ready_answers()
        original.site_name = "Stadium A"
        original.atem_enabled = True
        settings = svc.to_app_settings(original)
        back = svc.answers_from_settings(settings)
        assert back.site_name == "Stadium A"
        assert back.atem_enabled is True
        assert [c.role for c in back.cameras] == [c.role for c in original.cameras]

    def test_answers_from_settings_ors_atem_enabled_with_features_flag(self):
        """config/defaults/standard.yaml (and legacy_migration.py) only set
        features.atem_enabled — the atem: block's own `enabled` key is left at
        its dataclass default (False). Repair must not pre-fill the ATEM
        checkbox unchecked for an install that's actually on by that older
        flag, or an unnoticed save would silently disable it via
        _merge_onto_existing()."""
        svc = ProvisioningService()
        settings = svc.to_app_settings(_ready_answers())
        from dataclasses import replace
        drifted = replace(
            settings,
            atem=replace(settings.atem, enabled=False),
            features=replace(settings.features, atem_enabled=True),
        )
        back = svc.answers_from_settings(drifted)
        assert back.atem_enabled is True

    def test_answers_from_settings_drops_passwords(self):
        svc = ProvisioningService()
        settings = svc.to_app_settings(_ready_answers())
        back = svc.answers_from_settings(settings)
        # Secrets are not part of config.yaml, so passwords cannot round-trip.
        assert back.entry_password == ""
        assert back.admin_password == ""

    def test_load_existing_answers_reads_written_config(self, isolated):
        svc = ProvisioningService()
        ready = _ready_answers()
        ready.site_name = "Repaired Venue"
        svc.apply_files(ready, resolver=isolated)
        loaded = svc.load_existing_answers(isolated)
        assert loaded is not None
        assert loaded.site_name == "Repaired Venue"

    def test_load_existing_answers_none_when_absent(self, isolated):
        assert ProvisioningService().load_existing_answers(isolated) is None


class TestApplyFilesPreservesUnmodeledFields:
    """apply_files() must not silently reset fields the wizard doesn't model.

    ProvisioningAnswers only carries site identity, cameras, ATEM ip/enabled and
    network profile. Before the fix, apply_files() always wrote a from-scratch
    AppSettings, wiping runtime.data_dir, network.av_subnet/notes, ATEM's PiP
    nudge/input labels and other feature flags to dataclass defaults on every
    run — invisible on a bare-defaults fresh install, destructive on Repair.
    """

    def test_repair_preserves_runtime_settings(self, isolated):
        svc = ProvisioningService()
        svc.apply_files(_ready_answers(), resolver=isolated)
        config_path = isolated.config_dir / "config.yaml"
        raw = config_path.read_text(encoding="utf-8")
        # Hand-edit a field the wizard never models, simulating a prior
        # customization (e.g. done manually or by a future admin UI).
        raw = raw.replace('mode: production', 'mode: maintenance')
        config_path.write_text(raw, encoding="utf-8")

        repair_answers = _ready_answers()
        repair_answers.site_name = "Repaired Venue"
        svc.apply_files(repair_answers, resolver=isolated)

        reloaded = load_config(config_path)
        assert reloaded.site.name == "Repaired Venue"      # wizard-edited field applied
        assert reloaded.runtime.mode == "maintenance"       # unmodeled field preserved

    def test_repair_preserves_network_subnet_and_notes(self, isolated):
        svc = ProvisioningService()
        svc.apply_files(_ready_answers(), resolver=isolated)
        config_path = isolated.config_dir / "config.yaml"
        raw = config_path.read_text(encoding="utf-8")
        raw = raw.replace("notes: ''", 'notes: "Handover: static IPs assigned by IT"')
        raw = raw.replace("av_subnet: ''", 'av_subnet: "192.168.30.0/24"')
        config_path.write_text(raw, encoding="utf-8")

        repair_answers = _ready_answers()
        repair_answers.network_profile = "isolated_av_vlan"
        svc.apply_files(repair_answers, resolver=isolated)

        reloaded = load_config(config_path)
        assert reloaded.network.profile == "isolated_av_vlan"  # wizard-edited field applied
        assert reloaded.network.av_subnet == "192.168.30.0/24"  # unmodeled field preserved
        assert reloaded.network.notes == "Handover: static IPs assigned by IT"

    def test_repair_preserves_atem_pip_nudge(self, isolated):
        svc = ProvisioningService()
        answers = _ready_answers()
        answers.atem_enabled = True
        svc.apply_files(answers, resolver=isolated)
        config_path = isolated.config_dir / "config.yaml"
        raw = config_path.read_text(encoding="utf-8")
        raw = raw.replace("pan_speed: 0", "pan_speed: 12")
        config_path.write_text(raw, encoding="utf-8")

        repair_answers = _ready_answers()
        repair_answers.atem_enabled = True
        repair_answers.atem_ip = "172.16.1.99"
        svc.apply_files(repair_answers, resolver=isolated)

        reloaded = load_config(config_path)
        assert reloaded.atem.ip == "172.16.1.99"          # wizard-edited field applied
        assert reloaded.atem.pip_nudge.pan_speed == 12     # unmodeled field preserved

    def test_repair_rewrites_seeded_profile_to_match_camera_count(self, isolated):
        """The installer seeds config.yaml with 'starter_1_camera' before the
        wizard runs. Two things must hold after `hallptz setup`:

        1. The bogus hardcoded 'wizard' value is never written — it is not a
           known installation_profile and would make `hallptz doctor` warn.
        2. The seeded profile is corrected to match the cameras actually
           configured. Preserving 'starter_1_camera' on a two-camera install
           left the appliance permanently reporting
           "Profile mismatch: 'starter_1_camera' expects 1 camera(s) but 2
           configured" with no way to fix it from the wizard (#886).
        """
        from config.writer import write_full_config
        svc = ProvisioningService()
        starter = svc.to_app_settings(ProvisioningAnswers())
        from dataclasses import replace
        starter = replace(starter, site=replace(starter.site, installation_profile="starter_1_camera"))
        write_full_config(starter, isolated.config_dir / "config.yaml")

        answers = _ready_answers()
        assert len(answers.cameras) == 2  # guards the premise of this test
        svc.apply_files(answers, resolver=isolated)

        reloaded = load_config(isolated.config_dir / "config.yaml")
        assert reloaded.site.installation_profile == "standard_2_camera"
        assert reloaded.site.installation_profile != "wizard"

    def test_merge_preserves_installation_id_over_blank_wizard_answers(self, isolated):
        """Reproduces the actual bug scenario: on first boot the wizard user's
        `hallptz` group membership may not be active yet (pre-relogin), so
        cmd_setup's prefill silently fails and the wizard opens with blank
        ProvisioningAnswers (installation_id=""). apply_files() runs on the
        privileged (root) side and CAN read the existing config.yaml — the
        merge must not let that blank answer overwrite the installer's real,
        already-generated id."""
        from config.writer import write_full_config
        svc = ProvisioningService()
        starter = svc.to_app_settings(ProvisioningAnswers())
        from dataclasses import replace
        starter = replace(
            starter, site=replace(starter.site, installation_id="HALLPTZ-2026-STARTER99")
        )
        write_full_config(starter, isolated.config_dir / "config.yaml")

        blank_answers = ProvisioningAnswers(entry_password="a", admin_password="b")
        assert blank_answers.installation_id == ""
        svc.apply_files(blank_answers, resolver=isolated)

        reloaded = load_config(isolated.config_dir / "config.yaml")
        assert reloaded.site.installation_id == "HALLPTZ-2026-STARTER99"

    def test_fresh_install_unaffected_no_prior_config(self, isolated):
        """No config.yaml on disk yet — nothing to merge onto, behaves as before."""
        svc = ProvisioningService()
        svc.apply_files(_ready_answers(), resolver=isolated)
        reloaded = load_config(isolated.config_dir / "config.yaml")
        assert reloaded.site.name == "My Venue"
        assert reloaded.runtime.mode == "production"

    def test_corrupt_config_rescues_installation_id_via_raw_yaml(self, isolated):
        """A config.yaml with unrelated corruption (here: an invalid camera IP,
        which load_config() rejects) still has its site.installation_id/
        installation_profile rescued via a lenient raw-YAML read, rather than
        apply_files() silently writing a blank id — that id is what
        diagnostics/backup/licensing key off of."""
        config_path = isolated.config_dir / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "site:\n"
            "  name: Stadium\n"
            "  contact: IT\n"
            "  installation_profile: starter_1_camera\n"
            "  installation_id: HALLPTZ-2026-RESCUE01\n"
            "cameras:\n"
            "  - id: platform\n"
            "    role: platform\n"
            "    ip: not-a-valid-ip\n"
            "    visca_id: '81'\n"
            "atem:\n  ip: ''\n"
            "runtime:\n  data_dir: ''\n  connectivity_mode: offline\n  mode: production\n"
            "features:\n  atem_enabled: false\n  simulation: false\n"
            "network:\n  profile: flat_lan\n",
            encoding="utf-8",
        )
        # Sanity: this file really does fail strict load_config().
        with pytest.raises(Exception):
            load_config(config_path)

        ProvisioningService().apply_files(_ready_answers(), resolver=isolated)

        reloaded = load_config(config_path)  # apply_files() writes a clean config
        assert reloaded.site.installation_id == "HALLPTZ-2026-RESCUE01"
        assert reloaded.site.installation_profile == "starter_1_camera"

    def test_unparseable_config_falls_back_without_raising(self, isolated):
        """Even literally invalid YAML must not crash apply_files() — the
        rescue is itself best-effort and swallows its own failures."""
        config_path = isolated.config_dir / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("not: valid: yaml: [", encoding="utf-8")

        result = ProvisioningService().apply_files(_ready_answers(), resolver=isolated)
        assert result.ok is True
        reloaded = load_config(config_path)
        assert reloaded.site.name == "My Venue"  # falls back to wizard-only settings
