#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_wizard_bullseye_hardening.py — Regression tests for #886
#
# From the first physical Raspberry Pi install:
#   Could not parse stylesheet of object SetupWizard
#   Profile mismatch: 'starter_1_camera' expects 1 camera(s) but 2 configured
#   ATEM enabled but IP not configured
#
# A completed two-camera setup must not produce any of these.

from __future__ import annotations

import re

from application.provisioning_service import (
    CameraAnswer,
    ProvisioningAnswers,
    ProvisioningService,
)
from domain.installation_profile import (
    InstallationProfile,
    derive_installation_profile,
)
from ui.styles import error_label_qss, setup_wizard_qss


def _cameras(n: int) -> list[CameraAnswer]:
    return [
        CameraAnswer(id=f"cam{i}", role=f"role{i}", ip=f"172.16.1.{11 + i}",
                     visca_id=str(81 + i), name=f"Camera {i}")
        for i in range(n)
    ]


def _ready(**kwargs) -> ProvisioningAnswers:
    a = ProvisioningAnswers(**kwargs)
    a.entry_password = "operator-pw"
    a.admin_password = "admin-pw"
    return a


# ═══════════════════════════════════════════════════════════════════════════════
# Bullseye Qt 5.15 stylesheet compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestStylesheetIsBullseyeCompatible:
    def test_wizard_qss_uses_no_font_shorthand(self):
        """The `font:` shorthand with a numeric weight is what Qt 5.15 on
        Bullseye rejected, taking the whole sheet down with it."""
        qss = setup_wizard_qss()
        shorthand = re.findall(r"[^-]font\s*:", qss)
        assert not shorthand, f"font shorthand is unsafe on Bullseye Qt: {shorthand}"

    def test_error_label_qss_uses_no_font_shorthand(self):
        qss = error_label_qss()
        assert not re.findall(r"[^-]font\s*:", qss)

    def test_wizard_qss_uses_named_font_weights(self):
        """Numeric weights (600) are the unreliable part; `bold` is universal."""
        qss = setup_wizard_qss()
        numeric = re.findall(r"font-weight:\s*\d+", qss)
        assert not numeric, f"numeric font-weight is unsafe on Bullseye Qt: {numeric}"

    def test_wizard_qss_still_styles_the_key_widgets(self):
        """Guard against 'fixing' the parse error by deleting the styling."""
        qss = setup_wizard_qss()
        for selector in ("QWizard", "QGroupBox", "QLineEdit", "QComboBox",
                         "QCheckBox", "QPushButton"):
            assert selector in qss

    def test_braces_are_balanced(self):
        qss = setup_wizard_qss()
        assert qss.count("{") == qss.count("}")

    def test_every_stylesheet_in_the_module_is_balanced(self):
        """A stray brace from a doubled `}}` inside a *non*-f-string is what
        actually made Qt reject the wizard sheet. Guard every generator, not
        just the one that happened to break."""
        import inspect

        import ui.styles as styles

        unbalanced = []
        for name, fn in inspect.getmembers(styles, inspect.isfunction):
            if not name.endswith("qss"):
                continue
            try:
                sheet = fn()
            except TypeError:
                continue  # requires arguments; covered by its own test
            if sheet.count("{") != sheet.count("}"):
                unbalanced.append(name)
        assert not unbalanced, f"unbalanced QSS braces in: {unbalanced}"

    def test_no_block_closes_before_it_opens(self):
        depth = 0
        for char in setup_wizard_qss():
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                assert depth >= 0, "a '}' closes a block that was never opened"
        assert depth == 0


class TestApplyStylesheetSafely:
    def test_falls_back_to_native_when_qt_rejects_the_sheet(self, monkeypatch):
        """A rejected sheet must leave the wizard plain, not half-styled."""
        from PyQt5 import QtCore

        import ui.styles as styles

        class _Widget:
            def __init__(self):
                self.sheet = None

            def setStyleSheet(self, qss):
                self.sheet = qss

        def fake_install(handler):
            if handler is not None:
                # Simulate Qt emitting the parse warning during setStyleSheet.
                fake_install.handler = handler
            return None

        fake_install.handler = None
        monkeypatch.setattr(QtCore, "qInstallMessageHandler", fake_install)

        widget = _Widget()
        original_set = widget.setStyleSheet

        def set_and_warn(qss):
            original_set(qss)
            if fake_install.handler:
                fake_install.handler(0, None, "Could not parse stylesheet of object SetupWizard")

        widget.setStyleSheet = set_and_warn

        assert styles.apply_stylesheet_safely(widget, "QWizard { bogus }") is False
        assert widget.sheet == ""  # reverted to native styling

    def test_returns_true_and_keeps_sheet_when_accepted(self, monkeypatch):
        from PyQt5 import QtCore

        import ui.styles as styles

        class _Widget:
            def __init__(self):
                self.sheet = None

            def setStyleSheet(self, qss):
                self.sheet = qss

        monkeypatch.setattr(QtCore, "qInstallMessageHandler", lambda h: None)

        widget = _Widget()
        qss = setup_wizard_qss()
        assert styles.apply_stylesheet_safely(widget, qss) is True
        assert widget.sheet == qss

    def test_never_raises_when_qt_handler_is_unavailable(self, monkeypatch):
        from PyQt5 import QtCore

        import ui.styles as styles

        def boom(handler):
            raise RuntimeError("no message handler in this build")

        monkeypatch.setattr(QtCore, "qInstallMessageHandler", boom)

        class _Widget:
            def setStyleSheet(self, qss):
                self.sheet = qss

        assert styles.apply_stylesheet_safely(_Widget(), "QWizard {}") is True


# ═══════════════════════════════════════════════════════════════════════════════
# Installation profile is derived from the camera count
# ═══════════════════════════════════════════════════════════════════════════════

class TestProfileDerivation:
    def test_one_camera_gives_starter(self):
        assert derive_installation_profile(1) is InstallationProfile.STARTER_1_CAMERA

    def test_two_cameras_gives_standard(self):
        assert derive_installation_profile(2) is InstallationProfile.STANDARD_2_CAMERA

    def test_seeded_starter_is_corrected_for_two_cameras(self):
        """The exact real-device case: installer seeded starter, operator added a
        second camera."""
        result = derive_installation_profile(2, "starter_1_camera")
        assert result is InstallationProfile.STANDARD_2_CAMERA

    def test_two_cameras_reduced_to_one_is_corrected(self):
        result = derive_installation_profile(1, "standard_2_camera")
        assert result is InstallationProfile.STARTER_1_CAMERA

    def test_explicit_demo_profile_is_preserved(self):
        assert derive_installation_profile(2, "demo") is InstallationProfile.DEMO

    def test_explicit_custom_profile_is_preserved(self):
        assert derive_installation_profile(1, "custom") is InstallationProfile.CUSTOM

    def test_explicit_professional_profile_is_preserved(self):
        assert derive_installation_profile(2, "professional_multi_camera") \
            is InstallationProfile.PROFESSIONAL_MULTI_CAMERA

    def test_three_cameras_becomes_professional(self):
        assert derive_installation_profile(3) is InstallationProfile.PROFESSIONAL_MULTI_CAMERA

    def test_unknown_current_profile_is_ignored(self):
        """The old hardcoded 'wizard' value must not survive."""
        assert derive_installation_profile(2, "wizard") is InstallationProfile.STANDARD_2_CAMERA

    def test_no_cameras_falls_back_without_crashing(self):
        assert derive_installation_profile(0) is InstallationProfile.STARTER_1_CAMERA


class TestServiceAppliesDerivedProfile:
    def test_two_camera_answers_produce_standard_profile(self):
        settings = ProvisioningService().to_app_settings(_ready(cameras=_cameras(2)))
        assert settings.site.installation_profile == "standard_2_camera"

    def test_one_camera_answers_produce_starter_profile(self):
        settings = ProvisioningService().to_app_settings(_ready(cameras=_cameras(1)))
        assert settings.site.installation_profile == "starter_1_camera"

    def test_wizard_literal_is_never_written(self):
        settings = ProvisioningService().to_app_settings(_ready(cameras=_cameras(2)))
        assert settings.site.installation_profile != "wizard"

    def test_explicit_profile_answer_survives_round_trip(self):
        answers = _ready(cameras=_cameras(2), installation_profile="custom")
        settings = ProvisioningService().to_app_settings(answers)
        assert settings.site.installation_profile == "custom"

    def test_answers_from_settings_carries_the_profile_back(self):
        svc = ProvisioningService()
        settings = svc.to_app_settings(_ready(cameras=_cameras(2), installation_profile="custom"))
        assert svc.answers_from_settings(settings).installation_profile == "custom"

    def test_repair_round_trip_is_stable(self):
        """Repair mode must not drift the profile on a no-op edit."""
        svc = ProvisioningService()
        first = svc.to_app_settings(_ready(cameras=_cameras(2)))
        answers = svc.answers_from_settings(first)
        answers.entry_password = "operator-pw"
        answers.admin_password = "admin-pw"
        second = svc.to_app_settings(answers)
        assert second.site.installation_profile == first.site.installation_profile


# ═══════════════════════════════════════════════════════════════════════════════
# ATEM cannot be enabled without a valid IP
# ═══════════════════════════════════════════════════════════════════════════════

class TestAtemValidation:
    def _issue_fields(self, answers):
        return [i.field_path for i in ProvisioningService().validate(answers)]

    def test_enabled_with_blank_ip_is_blocking(self):
        answers = _ready(atem_enabled=True, atem_ip="")
        assert "atem_ip" in self._issue_fields(answers)

    def test_enabled_with_whitespace_ip_is_blocking(self):
        answers = _ready(atem_enabled=True, atem_ip="   ")
        assert "atem_ip" in self._issue_fields(answers)

    def test_enabled_with_malformed_ip_is_blocking(self):
        answers = _ready(atem_enabled=True, atem_ip="172.16.1")
        assert "atem_ip" in self._issue_fields(answers)

    def test_enabled_with_valid_ip_is_accepted(self):
        answers = _ready(atem_enabled=True, atem_ip="172.16.1.50")
        assert "atem_ip" not in self._issue_fields(answers)

    def test_disabled_with_blank_ip_is_fine(self):
        """ATEM off means its address is irrelevant — never block on it."""
        answers = _ready(atem_enabled=False, atem_ip="")
        assert "atem_ip" not in self._issue_fields(answers)

    def test_blocking_issue_carries_remediation(self):
        answers = _ready(atem_enabled=True, atem_ip="")
        issue = next(i for i in ProvisioningService().validate(answers)
                     if i.field_path == "atem_ip")
        assert issue.remediation


# ═══════════════════════════════════════════════════════════════════════════════
# Review screen separates blocking errors from deployment advice
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdvisoriesAreNotBlocking:
    def test_flat_lan_is_an_advisory_not_an_error(self):
        answers = _ready(network_profile="flat_lan", atem_enabled=True,
                         atem_ip="172.16.1.50")
        svc = ProvisioningService()
        assert svc.validate(answers) == []
        assert any(a.field_path == "network_profile" for a in svc.advisories(answers))

    def test_isolated_vlan_produces_no_network_advisory(self):
        answers = _ready(network_profile="isolated_av_vlan")
        advisories = ProvisioningService().advisories(answers)
        assert not any(a.field_path == "network_profile" for a in advisories)

    def test_disabled_atem_is_an_advisory_only(self):
        answers = _ready(atem_enabled=False)
        svc = ProvisioningService()
        assert not any(i.field_path == "atem_ip" for i in svc.validate(answers))
        assert any(a.field_path == "atem" for a in svc.advisories(answers))

    def test_advisories_never_block_completion(self):
        """A fully valid config with advisories must still be installable."""
        answers = _ready(network_profile="flat_lan", atem_enabled=False)
        svc = ProvisioningService()
        assert svc.validate(answers) == []
        assert svc.advisories(answers)  # advice exists, but Finish is not blocked


# ═══════════════════════════════════════════════════════════════════════════════
# A completed two-camera install produces no avoidable doctor warnings (#886 AC)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompletedStandardSetupIsClean:
    def test_two_camera_atem_setup_has_no_blocking_issues(self):
        answers = _ready(
            cameras=_cameras(2),
            atem_enabled=True,
            atem_ip="172.16.1.50",
            network_profile="isolated_av_vlan",
        )
        svc = ProvisioningService()
        assert svc.validate(answers) == []
        settings = svc.to_app_settings(answers)
        # The two warnings seen on the real device must both be absent.
        assert settings.site.installation_profile == "standard_2_camera"
        assert len(settings.cameras) == 2
        assert settings.atem.enabled is True
        assert settings.atem.ip == "172.16.1.50"

