#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
# tests/test_setup_wizard_rpi_pages.py — ui/setup_wizard/rpi_pages.py had no coverage
#
# These are the wizard pages actually used on the appliance (wizard.py imports
# DonePage/OptionalPage from here, not from the generic module). They exist to add
# the real-device lessons from the first Pi installation, and both of those
# additions were untested:
#
#   - the ATEM address is validated live rather than only on Next, and the module
#     docstring records why the override delegates to the base validation: an
#     emptiness-only check let "999.1.1" through the wizard.
#   - the Done page must not declare success when the privileged provisioning
#     step did not finish. It is the last screen an installer sees before leaving
#     the site.

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PyQt5")

from conftest import ensure_real_qt, is_poisoned_by_qt_stub   # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _real_qt():
    ensure_real_qt()


@pytest.fixture
def qapp(_real_qt):
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


class _WizardDouble:
    """The pages only ever reach the wizard for the shared answers object."""

    def __init__(self, answers):
        self.answers = answers


@pytest.fixture
def answers():
    from application.provisioning_service import ProvisioningAnswers
    return ProvisioningAnswers()


@pytest.fixture
def optional_page(qapp, answers):
    from ui.setup_wizard import rpi_pages
    if is_poisoned_by_qt_stub(rpi_pages.OptionalPage):
        pytest.skip("ui.setup_wizard.pages was imported under a PyQt5 stub — "
                    "run this file in isolation")
    return rpi_pages.OptionalPage(_WizardDouble(answers))


def notice_texts(page) -> list[str]:
    return [page._atem_error.text(), page._network_notice.text()]


class TestShippedPages:
    def test_the_wizard_uses_the_pi_variants(self):
        """A refactor that re-pointed wizard.py at the generic pages would
        silently drop every advisory below."""
        import ui.setup_wizard.wizard as wizard
        from ui.setup_wizard import rpi_pages

        assert wizard.OptionalPage is rpi_pages.OptionalPage
        assert wizard.DonePage is rpi_pages.DonePage

    def test_they_extend_rather_than_replace_the_generic_pages(self):
        from ui.setup_wizard import pages, rpi_pages

        assert issubclass(rpi_pages.OptionalPage, pages.OptionalPage)
        assert issubclass(rpi_pages.DonePage, pages.DonePage)


class TestAtemLiveValidation:
    def test_no_complaint_when_atem_is_not_used(self, optional_page):
        optional_page.atem_enabled.setChecked(False)
        assert optional_page._atem_error.text() == ""

    def test_enabling_atem_without_an_ip_asks_for_one(self, optional_page):
        """Shown while typing, not only after pressing Next."""
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("")
        assert "Enter its IP address" in optional_page._atem_error.text()

    def test_a_malformed_address_is_named(self, optional_page):
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("999.1.1")
        assert "'999.1.1' is not a valid IPv4 address." == optional_page._atem_error.text()

    def test_a_valid_address_clears_the_complaint(self, optional_page):
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("999.1.1")
        optional_page.atem_ip.setText("172.16.1.50")
        assert optional_page._atem_error.text() == ""

    def test_surrounding_whitespace_is_tolerated(self, optional_page):
        """Typed on a touchscreen keyboard."""
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("  172.16.1.50  ")
        assert optional_page._atem_error.text() == ""

    def test_disabling_atem_clears_a_stale_complaint(self, optional_page):
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("nonsense")
        optional_page.atem_enabled.setChecked(False)
        assert optional_page._atem_error.text() == ""


class TestNetworkProfileAdvisory:
    def test_a_flat_lan_is_allowed_but_flagged(self, optional_page):
        """It works for testing; production wants an isolated AV VLAN."""
        index = optional_page.profile.findData("flat_lan")
        assert index >= 0
        optional_page.profile.setCurrentIndex(index)
        assert "isolated AV VLAN is recommended" in optional_page._network_notice.text()

    def test_an_unconfirmed_profile_is_flagged(self, optional_page):
        index = optional_page.profile.findData("unknown")
        assert index >= 0
        optional_page.profile.setCurrentIndex(index)
        assert "not confirmed" in optional_page._network_notice.text()

    def test_the_recommended_profile_gets_no_advisory(self, optional_page):
        from domain.network_profile import NetworkProfile
        index = optional_page.profile.findData(NetworkProfile.ISOLATED_AV_VLAN.value)
        assert index >= 0, "the recommended profile is not offered"
        optional_page.profile.setCurrentIndex(index)
        assert optional_page._network_notice.text() == ""

    def test_every_offered_profile_is_a_known_one(self, optional_page):
        """A label with a value the domain does not know would be written into
        config.yaml and then fail validation on the next start."""
        from domain.network_profile import NetworkProfile
        known = {profile.value for profile in NetworkProfile}
        offered = {
            optional_page.profile.itemData(i)
            for i in range(optional_page.profile.count())
        }
        assert offered <= known, f"unknown profile values offered: {offered - known}"


class TestValidatePage:
    def test_a_valid_page_is_accepted(self, optional_page):
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("172.16.1.50")
        assert optional_page.validatePage() is True

    def test_a_malformed_address_blocks_next(self, optional_page):
        """The regression the docstring records: an emptiness-only check let
        '999.1.1' through."""
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("999.1.1")
        assert optional_page.validatePage() is False

    def test_an_empty_address_blocks_next(self, optional_page):
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("")
        assert optional_page.validatePage() is False

    def test_atem_disabled_is_never_blocked_by_its_ip(self, optional_page):
        optional_page.atem_enabled.setChecked(False)
        optional_page.atem_ip.setText("not-an-ip")
        assert optional_page.validatePage() is True

    def test_validation_refreshes_the_live_notices(self, optional_page):
        """Pressing Next on a page whose notice was cleared programmatically
        must still show why it was rejected."""
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("999.1.1")
        optional_page._atem_error.setText("")
        optional_page.validatePage()
        assert optional_page._atem_error.text() != ""

    def test_accepted_answers_reach_the_shared_object(self, optional_page, answers):
        """The base collect() must still run — the privileged step reads these."""
        optional_page.atem_enabled.setChecked(True)
        optional_page.atem_ip.setText("172.16.1.50")
        optional_page.validatePage()
        assert answers.atem_enabled is True
        assert answers.atem_ip == "172.16.1.50"


class TestDonePage:
    def _page(self, monkeypatch, ok: bool, summary: str):
        import ui.setup_wizard.rpi_pages as rpi_pages

        class _Verdict:
            def __init__(self):
                self.ok = ok

            def summary(self):
                return summary

        monkeypatch.setattr(rpi_pages, "verify_provisioned", lambda: _Verdict())
        from application.provisioning_service import ProvisioningAnswers
        page = rpi_pages.DonePage(_WizardDouble(ProvisioningAnswers()))
        page.initializePage()
        return page

    def test_a_successful_install_is_reported(self, qapp, monkeypatch):
        page = self._page(monkeypatch, True, "Install verified")
        assert page._verdict.text() == "Install verified"

    def test_a_successful_install_is_not_told_to_run_doctor(self, qapp, monkeypatch):
        page = self._page(monkeypatch, True, "Install verified")
        assert "doctor" not in page._verdict.text()

    def test_a_failed_verification_is_not_dressed_up_as_success(self, qapp, monkeypatch):
        """The marker is missing, so the privileged step did not finish — the
        installer must not walk away believing the room is ready."""
        page = self._page(monkeypatch, False, "Provisioning marker missing")
        assert "Provisioning marker missing" in page._verdict.text()

    def test_a_failure_names_the_next_step(self, qapp, monkeypatch):
        page = self._page(monkeypatch, False, "Provisioning marker missing")
        assert "hallptz doctor" in page._verdict.text()

    def test_the_verdict_is_rendered_as_plain_text(self, qapp, monkeypatch):
        """#886: a verdict containing stray markup or braces must not be parsed
        — Qt 5.15 on Bullseye is what made this matter."""
        from PyQt5.QtCore import Qt
        page = self._page(monkeypatch, False, "config <broken> {qss}")
        assert page._verdict.textFormat() == Qt.PlainText
        assert "config <broken> {qss}" in page._verdict.text()

    def test_verification_runs_on_page_entry_not_at_build_time(self, qapp, monkeypatch):
        """Built before the privileged step runs; only initializePage may ask."""
        import ui.setup_wizard.rpi_pages as rpi_pages
        from application.provisioning_service import ProvisioningAnswers

        calls = []
        monkeypatch.setattr(
            rpi_pages, "verify_provisioned",
            lambda: calls.append("checked") or type("V", (), {
                "ok": True, "summary": lambda self: "ok"})(),
        )
        page = rpi_pages.DonePage(_WizardDouble(ProvisioningAnswers()))
        assert calls == []
        page.initializePage()
        assert calls == ["checked"]
