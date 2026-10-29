#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Offscreen tests for the setup wizard GUI (QT_QPA_PLATFORM=offscreen via conftest).

Qt and the wizard are imported lazily inside fixtures, never at module top: other
test modules inject bare PyQt5 stubs into sys.modules at collection time (e.g.
test_login_screen_password_warning), and those stubs lack QWizard. The _real_qt
fixture drops any stub and loads the real PyQt5 before the wizard is imported, so
these tests exercise the genuine widgets.
"""

from __future__ import annotations

import sys

import pytest

from application.provisioning_service import ProvisioningService
from conftest import ensure_real_qt, is_poisoned_by_qt_stub
from config.loader import load_config
from runtime import secret_manager
from runtime.path_resolver import RuntimePathResolver


@pytest.fixture(scope="module", autouse=True)
def _real_qt():
    """Ensure the real PyQt5 is in sys.modules (drop any collection-time stub)."""
    ensure_real_qt()


@pytest.fixture
def _qapp(_real_qt):
    # Function-scoped, not module-scoped: under pytest-forked each test runs in
    # its own forked child, so a QApplication built once and shared across
    # tests in this module would be inherited across fork() boundaries from
    # whichever test happened to build it first — Qt does not support that and
    # aborts the next child that touches it. conftest.py's autouse
    # _qapp_available fixture already guarantees one exists in *this* process.
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def wizard(_qapp):
    from ui.setup_wizard import SetupWizard
    if is_poisoned_by_qt_stub(SetupWizard):
        pytest.skip("ui.setup_wizard was imported under a PyQt5 stub by another "
                    "test module — run this file in isolation")
    return SetupWizard()


@pytest.fixture
def repair_wizard(_qapp):
    """A wizard built the way Repair (`khptz setup --force` on a provisioned
    install) constructs it — with the admin sign-in gate as the first page."""
    from ui.setup_wizard import SetupWizard
    return SetupWizard(require_admin_auth=True)


def _page(wizard, name: str):
    for pid in wizard.pageIds():
        page = wizard.page(pid)
        if type(page).__name__ == name:
            return page
    raise AssertionError(f"page {name} not found")


class TestPagesCollect:

    def test_room_details_collected(self, wizard):
        page = _page(wizard, "RoomDetailsPage")
        page.name.setText("Main Hall")
        page.contact.setText("AV Team")
        assert page.validatePage() is True
        assert wizard.answers.site_name == "Main Hall"
        assert wizard.answers.site_contact == "AV Team"

    def test_blank_room_name_falls_back_to_default(self, wizard):
        page = _page(wizard, "RoomDetailsPage")
        page.name.setText("   ")
        page.collect()
        assert wizard.answers.site_name == "My Venue"

    def test_cameras_collected(self, wizard):
        page = _page(wizard, "CamerasPage")
        cam, name, ip, visca = page._rows[0]
        name.setText("Stage Cam")
        ip.setText("10.0.0.5")
        visca.setText("81")
        page.collect()
        assert wizard.answers.cameras[0].name == "Stage Cam"
        assert wizard.answers.cameras[0].ip == "10.0.0.5"


class TestCamerasPageAddRemove:
    """The installer seeds config/defaults/starter.yaml — ONE camera — and
    cmd_setup pre-fills the wizard from that config.yaml. Without add/remove
    here, a two-camera room (the product's normal shape: `platform` for the
    first seats, `comments` for the rest — see application/preset_sources.py)
    was unreachable through setup or repair, and /etc/khptz is root:khptz 0640
    so the desktop user cannot fix it by hand either."""

    def _single_camera_page(self, wizard):
        from application.provisioning_service import CameraAnswer
        wizard.answers.cameras = [
            CameraAnswer(id="platform", role="platform", ip="172.16.1.11",
                         visca_id="81", name="Main Platform")
        ]
        page = _page(wizard, "CamerasPage")
        page._rebuild()
        return page

    def test_add_appends_the_comments_camera(self, wizard):
        page = self._single_camera_page(wizard)
        assert len(page._rows) == 1
        page._on_add()
        assert len(wizard.answers.cameras) == 2
        assert len(page._rows) == 2
        assert wizard.answers.cameras[1].role == "comments"

    def test_added_camera_passes_validation(self, wizard):
        """An added camera must not collide on id, IP or visca_id — the
        operator would be stuck on Review with no way to fix it here."""
        from application.provisioning_service import ProvisioningService
        page = self._single_camera_page(wizard)
        page._on_add()
        wizard.answers.entry_password = "op-pw"
        wizard.answers.admin_password = "admin-pw"
        assert ProvisioningService().validate(wizard.answers) == []

    def test_edits_survive_pressing_add(self, wizard):
        """_rebuild() replaces the widgets, so anything typed but not yet
        collected would be lost if _on_add did not collect first."""
        page = self._single_camera_page(wizard)
        _cam, name, ip, _visca = page._rows[0]
        name.setText("Camara Tribuna")
        ip.setText("192.168.10.21")
        page._on_add()
        assert wizard.answers.cameras[0].name == "Camara Tribuna"
        assert wizard.answers.cameras[0].ip == "192.168.10.21"

    def test_remove_drops_the_right_camera(self, wizard):
        page = self._single_camera_page(wizard)
        page._on_add()
        page._rows[1][1].setText("Second")
        page._on_remove(1)
        assert len(wizard.answers.cameras) == 1
        assert wizard.answers.cameras[0].role == "platform"

    def test_cannot_remove_the_last_camera(self, wizard):
        page = self._single_camera_page(wizard)
        page._on_remove(0)
        assert len(wizard.answers.cameras) == 1
        assert "at least one camera" in page._error.text().lower()

    def test_no_remove_button_rendered_for_a_single_camera(self, wizard):
        from PyQt5.QtWidgets import QPushButton
        page = self._single_camera_page(wizard)
        removes = [b for box in page._boxes for b in box.findChildren(QPushButton)]
        assert removes == []
        page._on_add()
        removes = [b for box in page._boxes for b in box.findChildren(QPushButton)]
        assert len(removes) == 2, "both cameras should be removable once there are two"


class TestNextCameraAnswer:
    """Pure rule behind the Add button — no Qt, so it is exhaustively testable."""

    def _cam(self, **kw):
        from application.provisioning_service import CameraAnswer
        base = dict(id="platform", role="platform", ip="172.16.1.11", visca_id="81")
        base.update(kw)
        return CameraAnswer(**base)

    def test_first_add_is_the_comments_camera(self):
        from application.provisioning_service import next_camera_answer
        added = next_camera_answer([self._cam()])
        assert added.role == "comments"
        assert added.id == "comments"
        assert added.visca_id == "82"
        assert added.ip == "172.16.1.12"

    def test_third_camera_gets_a_generic_role(self):
        from application.provisioning_service import next_camera_answer
        existing = [self._cam(), self._cam(id="comments", role="comments",
                                          ip="172.16.1.12", visca_id="82")]
        added = next_camera_answer(existing)
        assert added.role not in ("platform", "comments")
        assert added.visca_id == "83"

    def test_never_collides_on_id_ip_or_visca(self):
        from application.provisioning_service import next_camera_answer
        cams = [self._cam()]
        for _ in range(6):
            cams.append(next_camera_answer(cams))
        assert len({c.id for c in cams}) == len(cams)
        assert len({c.ip for c in cams}) == len(cams)
        assert len({c.visca_id for c in cams}) == len(cams)

    def test_ip_wraps_without_producing_a_network_address(self):
        from application.provisioning_service import next_camera_answer
        added = next_camera_answer([self._cam(ip="10.0.0.255")])
        assert not added.ip.endswith(".0")
        assert added.ip != "10.0.0.255"

    def test_added_camera_has_a_display_name(self):
        from application.provisioning_service import next_camera_answer
        assert next_camera_answer([self._cam()]).name == "Comments"


class TestOptionalPage:

    def test_atem_toggle_and_network_collected(self, wizard):
        page = _page(wizard, "OptionalPage")
        page.atem_enabled.setChecked(True)
        page.atem_ip.setText("10.0.0.50")
        page._select_profile("isolated_av_vlan")
        page.collect()
        assert wizard.answers.atem_enabled is True
        assert wizard.answers.atem_ip == "10.0.0.50"
        assert wizard.answers.network_profile == "isolated_av_vlan"

    def test_defaults_preserved_when_untouched(self, wizard):
        page = _page(wizard, "OptionalPage")
        page.collect()
        assert wizard.answers.atem_enabled is False
        assert wizard.answers.network_profile == "flat_lan"


class TestDeviceCheckPage:

    def test_initialize_runs_checks_and_completes_on_dev(self, wizard):
        page = _page(wizard, "DeviceCheckPage")
        page.initializePage()
        # PyQt5 is importable in the test env, so nothing blocking → complete.
        assert page.isComplete() is True


class TestPasswordsPage:

    def test_mismatch_blocks_and_reports(self, wizard):
        page = _page(wizard, "PasswordsPage")
        page.entry.setText("aaa")
        page.entry_confirm.setText("bbb")
        assert page.validatePage() is False
        assert "match" in page.error_text().lower()

    def test_entry_equal_admin_blocked(self, wizard):
        page = _page(wizard, "PasswordsPage")
        for f in (page.entry, page.entry_confirm, page.admin, page.admin_confirm):
            f.setText("same")
        assert page.validatePage() is False

    def test_valid_passwords_pass_and_collect(self, wizard):
        page = _page(wizard, "PasswordsPage")
        page.entry.setText("op-pass")
        page.entry_confirm.setText("op-pass")
        page.admin.setText("admin-pass")
        page.admin_confirm.setText("admin-pass")
        assert page.validatePage() is True
        assert wizard.answers.entry_password == "op-pass"
        assert wizard.answers.admin_password == "admin-pass"


class TestReviewGating:

    def test_review_incomplete_until_passwords_set(self, wizard):
        review = _page(wizard, "ReviewPage")
        review.initializePage()
        assert review.isComplete() is False

    def test_review_complete_once_ready(self, wizard):
        wizard.answers.entry_password = "op"
        wizard.answers.admin_password = "ad"
        review = _page(wizard, "ReviewPage")
        review.initializePage()
        assert review.isComplete() is True


class _FakeHandoff:
    """Stand-in for ProvisionHandoff: records begin() and returns a queued result."""

    poll_interval_s = 0.01

    def __init__(self, result=None):
        self._result = result
        self.began_with = None

    def begin(self, answers):
        self.began_with = answers

    def poll(self):
        return self._result


class TestInstallingPage:

    def test_initialize_drops_request_and_blocks_until_done(self, _qapp):
        from ui.setup_wizard import SetupWizard

        handoff = _FakeHandoff(result=None)  # not finished yet
        wizard = SetupWizard(handoff=handoff)
        page = _page(wizard, "InstallingPage")
        page.initializePage()
        assert handoff.began_with is wizard.answers
        assert page.isComplete() is False  # Next disabled while provisioning
        page._timer.stop()  # we drive _poll_once manually; don't leave it running

    def test_success_completes_page(self, _qapp):
        from application.provision_handoff import HandoffResult
        from ui.setup_wizard import SetupWizard

        ok = HandoffResult(ok=True, written=["/etc/khptz/config.yaml"])
        wizard = SetupWizard(handoff=_FakeHandoff(result=ok))
        page = _page(wizard, "InstallingPage")
        page.initializePage()
        page._poll_once()
        assert page.isComplete() is True
        assert "complete" in page._status.text().lower()

    def test_failure_keeps_page_incomplete(self, _qapp):
        from application.provision_handoff import HandoffResult
        from ui.setup_wizard import SetupWizard

        bad = HandoffResult(ok=False, error="boom")
        wizard = SetupWizard(handoff=_FakeHandoff(result=bad))
        page = _page(wizard, "InstallingPage")
        page.initializePage()
        page._poll_once()
        assert page.isComplete() is False  # cannot advance to Done on failure
        assert "boom" in page._status.text()


class TestDonePageVerification:

    def test_done_warns_when_marker_missing(self, _qapp, tmp_path, monkeypatch):
        from ui.setup_wizard import SetupWizard

        monkeypatch.setenv("KHPTZ_CONFIG_DIR", str(tmp_path / "etc"))
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "data"))
        wizard = SetupWizard()
        done = _page(wizard, "DonePage")
        done.initializePage()  # nothing provisioned in this temp tree
        assert "doctor" in done._verdict.text().lower()

    def test_done_confirms_when_provisioned(self, _qapp, tmp_path, monkeypatch):
        from ui.setup_wizard import SetupWizard

        monkeypatch.setenv("KHPTZ_CONFIG_DIR", str(tmp_path / "etc"))
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(tmp_path / "data"))
        resolver = RuntimePathResolver()
        resolver.config_dir.mkdir(parents=True, exist_ok=True)
        (resolver.config_dir / "config.yaml").write_text("x", encoding="utf-8")
        resolver.provisioned_marker_file.write_text("ok\n", encoding="utf-8")

        wizard = SetupWizard()
        done = _page(wizard, "DonePage")
        done.initializePage()
        assert "verified" in done._verdict.text().lower()


class TestAdminAuthPage:
    """Repair (require_admin_auth=True) shows an admin sign-in page first, but
    it only COLLECTS the password — the wizard's own (desktop-session)
    process cannot reliably decrypt the khptz:khptz-owned admin secret to
    verify it itself. Real verification happens in the privileged
    runtime.provision.run_provision() (see TestAdminAuthVerification in
    test_provision_entrypoint.py). See PR #867 review."""

    def test_normal_wizard_has_no_auth_page(self, wizard):
        """A plain SetupWizard() (fresh install) never shows this page."""
        with pytest.raises(AssertionError):
            _page(wizard, "AdminAuthPage")

    def test_repair_wizard_starts_on_auth_page(self, repair_wizard):
        first = repair_wizard.page(repair_wizard.pageIds()[0])
        assert type(first).__name__ == "AdminAuthPage"

    def test_advancing_always_succeeds_and_collects_password(self, repair_wizard):
        """No client-side verify_admin call — advancing always succeeds; the
        typed password is collected for the privileged side to check."""
        page = _page(repair_wizard, "AdminAuthPage")
        page._password.setText("whatever-was-typed")
        assert page.validatePage() is True
        assert repair_wizard.answers.current_admin_password == "whatever-was-typed"


class TestEndToEndApply:
    """Driving the wizard answers through the engine produces a working install."""

    def test_collected_answers_apply_to_files(self, _qapp, tmp_path, monkeypatch):
        from ui.setup_wizard import SetupWizard

        data_dir = tmp_path / "data"
        monkeypatch.setenv("KHPTZ_CONFIG_DIR", str(tmp_path / "etc"))
        monkeypatch.setenv("KHPTZ_DATA_DIR", str(data_dir))
        monkeypatch.setattr(secret_manager, "_CONFIG_DIR", data_dir)
        monkeypatch.setattr(secret_manager, "_ENC_FILE", data_dir / "password.enc")

        wizard = SetupWizard()
        pw = _page(wizard, "PasswordsPage")
        pw.entry.setText("op-pass")
        pw.entry_confirm.setText("op-pass")
        pw.admin.setText("admin-pass")
        pw.admin_confirm.setText("admin-pass")
        assert pw.validatePage() is True

        resolver = RuntimePathResolver()
        result = ProvisioningService().apply_files(wizard.answers, resolver=resolver)
        assert result.ok is True

        loaded = load_config(resolver.config_dir / "config.yaml")
        assert len(loaded.cameras) == 2
        assert secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN) == "admin-pass"
