#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""
test_network_profile.py — Tests for domain/network_profile.py and the network
profile diagnostic check (#505, #506, #509).

Covers:
- NetworkProfile: parse valid, parse invalid → None, KNOWN_PROFILE_VALUES
- is_safe_profile: isolated_av_vlan True, flat_lan False, unknown False
- is_risk_profile: flat_lan True, isolated_av_vlan False
- NetworkProfileConfig.from_dict: missing keys use safe defaults
- validate_network_profile: unknown profile → issue, valid → no issues
- validate_network_profile: invalid subnet format → issue
- validate_network_profile: invalid VLAN ID → issue
- validate_network_profile: VLAN out of range → issue
- validate_network_profile: guest_access_allowed=True → issue
- Flat-network warning / action messages are non-empty strings
- DiagnosticsService: flat_lan → WARNING with remediation
- DiagnosticsService: isolated_av_vlan → OK
- DiagnosticsService: unknown profile → WARNING
- DiagnosticsService: no network section → WARNING (safe for existing installs)
- NetworkSettings loaded from config without network key (existing install safe)
- AppSettings.network defaults to NetworkSettings() when not present in config
"""
from __future__ import annotations


from domain.network_profile import (
    NetworkProfile,
    NetworkProfileConfig,
    KNOWN_PROFILE_VALUES,
    flat_network_action,
    flat_network_warning_message,
    is_risk_profile,
    is_safe_profile,
    parse_network_profile,
    validate_network_profile,
)


# ── NetworkProfile enum ───────────────────────────────────────────────────────

class TestNetworkProfileEnum:

    def test_isolated_av_vlan_value(self):
        assert NetworkProfile.ISOLATED_AV_VLAN.value == "isolated_av_vlan"

    def test_flat_lan_value(self):
        assert NetworkProfile.FLAT_LAN.value == "flat_lan"

    def test_unknown_value(self):
        assert NetworkProfile.UNKNOWN.value == "unknown"

    def test_known_profile_values_contains_all(self):
        for m in NetworkProfile:
            assert m.value in KNOWN_PROFILE_VALUES

    def test_parse_valid_isolated(self):
        assert parse_network_profile("isolated_av_vlan") is NetworkProfile.ISOLATED_AV_VLAN

    def test_parse_valid_flat_lan(self):
        assert parse_network_profile("flat_lan") is NetworkProfile.FLAT_LAN

    def test_parse_valid_unknown(self):
        assert parse_network_profile("unknown") is NetworkProfile.UNKNOWN

    def test_parse_invalid_returns_none(self):
        assert parse_network_profile("corporate_lan") is None

    def test_parse_case_insensitive(self):
        assert parse_network_profile("ISOLATED_AV_VLAN") is NetworkProfile.ISOLATED_AV_VLAN

    def test_is_safe_only_for_isolated(self):
        assert is_safe_profile(NetworkProfile.ISOLATED_AV_VLAN)
        assert not is_safe_profile(NetworkProfile.FLAT_LAN)
        assert not is_safe_profile(NetworkProfile.UNKNOWN)

    def test_is_risk_for_flat_and_unknown(self):
        assert is_risk_profile(NetworkProfile.FLAT_LAN)
        assert is_risk_profile(NetworkProfile.UNKNOWN)
        assert not is_risk_profile(NetworkProfile.ISOLATED_AV_VLAN)


# ── NetworkProfileConfig ──────────────────────────────────────────────────────

class TestNetworkProfileConfig:

    def test_from_dict_empty_uses_safe_defaults(self):
        cfg = NetworkProfileConfig.from_dict({})
        assert cfg.profile is NetworkProfile.UNKNOWN
        assert cfg.av_subnet is None
        assert cfg.av_vlan_id is None
        assert cfg.guest_access_allowed is None
        assert cfg.internet_required is False

    def test_from_dict_parses_profile(self):
        cfg = NetworkProfileConfig.from_dict({"profile": "isolated_av_vlan"})
        assert cfg.profile is NetworkProfile.ISOLATED_AV_VLAN

    def test_from_dict_unknown_profile_maps_to_unknown(self):
        cfg = NetworkProfileConfig.from_dict({"profile": "corporate"})
        assert cfg.profile is NetworkProfile.UNKNOWN

    def test_from_dict_parses_subnet(self):
        cfg = NetworkProfileConfig.from_dict({"av_subnet": "192.168.30.0/24"})
        assert cfg.av_subnet == "192.168.30.0/24"

    def test_from_dict_parses_vlan_id(self):
        cfg = NetworkProfileConfig.from_dict({"av_vlan_id": "30"})
        assert cfg.av_vlan_id == "30"

    def test_from_dict_parses_guest_access(self):
        cfg = NetworkProfileConfig.from_dict({"guest_access_allowed": True})
        assert cfg.guest_access_allowed is True

    def test_to_dict_has_required_keys(self):
        cfg = NetworkProfileConfig.from_dict({"profile": "flat_lan"})
        d = cfg.to_dict()
        assert "profile" in d
        assert "av_subnet" in d
        assert "guest_access_allowed" in d


# ── validate_network_profile ──────────────────────────────────────────────────

class TestValidateNetworkProfile:

    def test_unknown_profile_produces_issue(self):
        cfg = NetworkProfileConfig.from_dict({})
        issues = validate_network_profile(cfg)
        assert any("profile" in i.field for i in issues)

    def test_isolated_av_vlan_no_issues(self):
        cfg = NetworkProfileConfig.from_dict({"profile": "isolated_av_vlan"})
        issues = validate_network_profile(cfg)
        assert issues == []

    def test_flat_lan_no_schema_issues(self):
        # flat_lan is a valid value; no schema issues (warning from diagnostic check)
        cfg = NetworkProfileConfig.from_dict({"profile": "flat_lan"})
        issues = validate_network_profile(cfg)
        assert issues == []

    def test_invalid_subnet_format_produces_issue(self):
        cfg = NetworkProfileConfig.from_dict({
            "profile": "isolated_av_vlan",
            "av_subnet": "not-a-subnet",
        })
        issues = validate_network_profile(cfg)
        assert any("subnet" in i.field for i in issues)

    def test_valid_subnet_no_issue(self):
        cfg = NetworkProfileConfig.from_dict({
            "profile": "isolated_av_vlan",
            "av_subnet": "192.168.30.0/24",
        })
        issues = validate_network_profile(cfg)
        assert issues == []

    def test_invalid_vlan_id_format_produces_issue(self):
        cfg = NetworkProfileConfig.from_dict({
            "profile": "isolated_av_vlan",
            "av_vlan_id": "abc",
        })
        issues = validate_network_profile(cfg)
        assert any("vlan" in i.field.lower() for i in issues)

    def test_vlan_id_out_of_range_produces_issue(self):
        cfg = NetworkProfileConfig.from_dict({
            "profile": "isolated_av_vlan",
            "av_vlan_id": "5000",
        })
        issues = validate_network_profile(cfg)
        assert any("vlan" in i.field.lower() for i in issues)

    def test_valid_vlan_id_no_issue(self):
        cfg = NetworkProfileConfig.from_dict({
            "profile": "isolated_av_vlan",
            "av_vlan_id": "30",
        })
        assert validate_network_profile(cfg) == []

    def test_guest_access_allowed_produces_issue(self):
        cfg = NetworkProfileConfig.from_dict({
            "profile": "isolated_av_vlan",
            "guest_access_allowed": True,
        })
        issues = validate_network_profile(cfg)
        assert any("guest" in i.field for i in issues)

    def test_guest_access_false_no_issue(self):
        cfg = NetworkProfileConfig.from_dict({
            "profile": "isolated_av_vlan",
            "guest_access_allowed": False,
        })
        assert validate_network_profile(cfg) == []


# ── Warning messages ──────────────────────────────────────────────────────────

class TestFlatNetworkMessages:

    def test_warning_message_is_non_empty(self):
        msg = flat_network_warning_message()
        assert isinstance(msg, str)
        assert len(msg) > 20

    def test_action_message_is_non_empty(self):
        action = flat_network_action()
        assert isinstance(action, str)
        assert len(action) > 20

    def test_warning_mentions_flat_network(self):
        msg = flat_network_warning_message().lower()
        assert "flat" in msg or "vlan" in msg or "network" in msg

    def test_action_mentions_vlan(self):
        action = flat_network_action().lower()
        assert "vlan" in action


# ── Diagnostic check integration ──────────────────────────────────────────────

class TestNetworkProfileDiagnosticCheck:

    def _make_settings(self, profile="isolated_av_vlan", **kwargs):
        from config.settings import (
            AppSettings, ATEMSettings, CameraSettings, FeaturesSettings,
            NetworkSettings, RuntimeSettings, SiteSettings,
        )
        cam = CameraSettings(id="platform", role="platform", ip="192.168.30.20", visca_id="81")
        net = NetworkSettings(profile=profile, **kwargs)
        return AppSettings(
            site=SiteSettings(),
            cameras=[cam],
            atem=ATEMSettings(),
            runtime=RuntimeSettings(),
            features=FeaturesSettings(),
            network=net,
        )

    def test_isolated_av_vlan_produces_ok(self):
        from application.diagnostics_service import DiagnosticsService
        settings = self._make_settings(profile="isolated_av_vlan")
        svc = DiagnosticsService()
        result = svc._check_network_profile(settings)
        from application.diagnostics_service import Status
        assert result.status is Status.OK

    def test_flat_lan_produces_warning(self):
        from application.diagnostics_service import DiagnosticsService, Status
        settings = self._make_settings(profile="flat_lan")
        svc = DiagnosticsService()
        result = svc._check_network_profile(settings)
        assert result.status is Status.WARNING

    def test_flat_lan_warning_includes_remediation(self):
        from application.diagnostics_service import DiagnosticsService
        settings = self._make_settings(profile="flat_lan")
        svc = DiagnosticsService()
        result = svc._check_network_profile(settings)
        assert result.suggested_action is not None
        assert len(result.suggested_action) > 10

    def test_unknown_profile_produces_warning(self):
        from application.diagnostics_service import DiagnosticsService, Status
        settings = self._make_settings(profile="unknown")
        svc = DiagnosticsService()
        result = svc._check_network_profile(settings)
        assert result.status is Status.WARNING

    def test_no_settings_produces_warning(self):
        from application.diagnostics_service import DiagnosticsService, Status
        svc = DiagnosticsService()
        result = svc._check_network_profile(None)
        assert result.status is Status.WARNING

    def test_network_profile_check_does_not_block(self):
        from application.diagnostics_service import DiagnosticsService, Status
        settings = self._make_settings(profile="flat_lan")
        svc = DiagnosticsService()
        result = svc._check_network_profile(settings)
        # Must be WARNING, not FAIL — does not block demo/dev
        assert result.status is Status.WARNING
        assert result.blocking is False


# ── Config loader integration ─────────────────────────────────────────────────

class TestNetworkSettingsLoader:

    def test_existing_install_without_network_section_loads_safely(self, tmp_path):
        """An existing config.yaml without a 'network:' section must load without error."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
site:
  name: Test Site
cameras:
  - id: platform
    role: platform
    ip: "192.168.30.20"
    visca_id: "81"
atem:
  ip: ""
runtime:
  connectivity_mode: offline
features:
  atem_enabled: false
""",
            encoding="utf-8",
        )
        from config.loader import load_config
        settings = load_config(config_file)
        # Should default to NetworkSettings with profile="unknown"
        assert settings.network is not None
        assert settings.network.profile == "unknown"

    def test_config_with_network_section_parses_profile(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
site:
  name: Test Site
cameras:
  - id: platform
    role: platform
    ip: "192.168.30.20"
    visca_id: "81"
atem:
  ip: ""
runtime:
  connectivity_mode: offline
features:
  atem_enabled: false
network:
  profile: isolated_av_vlan
  av_subnet: "192.168.30.0/24"
  av_vlan_id: "30"
""",
            encoding="utf-8",
        )
        from config.loader import load_config
        settings = load_config(config_file)
        assert settings.network.profile == "isolated_av_vlan"
        assert settings.network.av_subnet == "192.168.30.0/24"
        assert settings.network.av_vlan_id == "30"

    def test_config_with_flat_lan_profile_parses(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            """
site:
  name: Test
cameras:
  - id: platform
    role: platform
    ip: "192.168.1.20"
    visca_id: "81"
atem:
  ip: ""
runtime:
  connectivity_mode: offline
features:
  atem_enabled: false
network:
  profile: flat_lan
""",
            encoding="utf-8",
        )
        from config.loader import load_config
        settings = load_config(config_file)
        assert settings.network.profile == "flat_lan"
