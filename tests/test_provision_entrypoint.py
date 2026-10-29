#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Tests for runtime.provision — the privileged provisioning entrypoint.

The OS-mutation half (do_system) is exercised only via plan_system_commands and
an injected runner; no real user/dirs/systemctl are touched. The request→apply→
result→shred flow is tested end-to-end against a temp tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from application.provisioning_service import ProvisioningAnswers
from config.loader import load_config
from runtime import provision, secret_manager
from runtime.path_resolver import RuntimePathResolver


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("HALLPTZ_CONFIG_DIR", str(tmp_path / "etc"))
    monkeypatch.setenv("HALLPTZ_DATA_DIR", str(data_dir))
    monkeypatch.setattr(secret_manager, "_CONFIG_DIR", data_dir)
    monkeypatch.setattr(secret_manager, "_ENC_FILE", data_dir / "password.enc")
    return RuntimePathResolver(), tmp_path


def _write_request(tmp_path, **overrides):
    answers = ProvisioningAnswers()
    answers.entry_password = "op-pass"
    answers.admin_password = "admin-pass"
    data = provision.answers_to_dict(answers)
    data.update(overrides)
    req = tmp_path / "request.json"
    req.write_text(json.dumps(data), encoding="utf-8")
    return req


class TestAnswersRoundTrip:

    def test_dict_round_trip(self):
        a = ProvisioningAnswers()
        a.entry_password = "x"
        a.admin_password = "y"
        back = provision.answers_from_dict(provision.answers_to_dict(a))
        assert back.entry_password == "x"
        assert [c.id for c in back.cameras] == [c.id for c in a.cameras]


class TestRunProvision:

    def test_happy_path_writes_and_shreds(self, isolated):
        resolver, tmp_path = isolated
        req = _write_request(tmp_path)
        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is True
        assert (resolver.config_dir / "config.yaml").exists()
        assert secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN) == "admin-pass"
        assert resolver.provisioned_marker_file.exists()
        assert not req.exists(), "request file must be shredded"

    def test_result_file_written(self, isolated):
        resolver, tmp_path = isolated
        req = _write_request(tmp_path)
        res_path = tmp_path / "result.json"
        provision.run_provision(req, res_path, resolver=resolver, do_system=False)
        assert json.loads(res_path.read_text(encoding="utf-8"))["ok"] is True

    def test_invalid_answers_report_and_no_marker(self, isolated):
        resolver, tmp_path = isolated
        req = _write_request(tmp_path, entry_password="")  # missing password
        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is False
        assert any("entry_password" in i["field"] for i in result["issues"])
        assert not resolver.provisioned_marker_file.exists()
        assert not req.exists(), "request must be shredded even on failure"

    def test_bad_ip_reported(self, isolated):
        resolver, tmp_path = isolated
        answers = ProvisioningAnswers()
        answers.entry_password = "a"
        answers.admin_password = "b"
        answers.cameras[0].ip = "999.0.0.1"
        data = provision.answers_to_dict(answers)
        req = tmp_path / "request.json"
        req.write_text(json.dumps(data), encoding="utf-8")
        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is False

    def test_corrupt_request_produces_error_result(self, isolated):
        resolver, tmp_path = isolated
        req = tmp_path / "request.json"
        req.write_text("not json{", encoding="utf-8")
        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is False
        assert "error" in result
        assert not req.exists()


class _CorruptThenFail(provision.ProvisioningService):
    """A service that writes a bad config then fails, to prove rollback works."""

    def apply_files(self, answers, resolver=None, **kw):  # noqa: ANN001
        (resolver.config_dir / "config.yaml").write_text("CORRUPT", encoding="utf-8")
        raise RuntimeError("apply blew up")


class TestAdminAuthVerification:
    """The privileged oneshot must enforce the admin-password check itself —
    not just the wizard's UI (AdminAuthPage), which cannot reliably decrypt
    the hallptz:hallptz-owned secret to verify it. /run/hallptz is writable by the
    unprivileged wizard user, so a raw request dropped there directly
    (bypassing the wizard entirely) must not be enough to reconfigure or
    reset passwords on an already-provisioned install. See PR #867 review."""

    def _provision_once(self, tmp_path, resolver):
        """Establish a provisioned install with a known admin password."""
        req = _write_request(tmp_path, admin_password="the-real-admin-pw")
        result = provision.run_provision(
            req, tmp_path / "r1.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is True
        assert resolver.provisioned_marker_file.exists()

    def test_wrong_current_admin_password_is_rejected(self, isolated):
        resolver, tmp_path = isolated
        self._provision_once(tmp_path, resolver)

        req = _write_request(
            tmp_path, site_name="Hijacked", current_admin_password="wrong-guess"
        )
        result = provision.run_provision(
            req, tmp_path / "r2.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is False
        assert any(
            i["field"] == "current_admin_password" for i in result.get("issues", [])
        )
        # Nothing was overwritten — the site name from the first provision stands.
        reloaded = load_config(resolver.config_dir / "config.yaml")
        assert reloaded.site.name != "Hijacked"

    def test_correct_current_admin_password_is_accepted(self, isolated):
        resolver, tmp_path = isolated
        self._provision_once(tmp_path, resolver)

        req = _write_request(
            tmp_path,
            site_name="Repaired Legit",
            current_admin_password="the-real-admin-pw",
        )
        result = provision.run_provision(
            req, tmp_path / "r2.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is True
        reloaded = load_config(resolver.config_dir / "config.yaml")
        assert reloaded.site.name == "Repaired Legit"

    def test_raw_request_cannot_bypass_via_missing_current_password(self, isolated):
        """The exact bypass this closes: a request built without ever going
        through AdminAuthPage (current_admin_password left at its default
        blank) must still be rejected on a provisioned install."""
        resolver, tmp_path = isolated
        self._provision_once(tmp_path, resolver)

        req = _write_request(tmp_path, site_name="Bypassed")
        result = provision.run_provision(
            req, tmp_path / "r2.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is False

    def test_fresh_install_does_not_require_current_admin_password(self, isolated):
        """Not yet provisioned — nothing to protect yet, no check applies."""
        resolver, tmp_path = isolated
        req = _write_request(tmp_path)  # current_admin_password left blank
        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is True


class TestSnapshotRollback:

    def test_repair_rollback_preserves_previous_config(self, isolated):
        resolver, tmp_path = isolated
        # First: a successful provision establishes the "known good" install.
        provision.run_provision(
            _write_request(tmp_path), tmp_path / "r1.json",
            resolver=resolver, do_system=False,
        )
        good_config = (resolver.config_dir / "config.yaml").read_bytes()
        assert secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN) == "admin-pass"

        # Second (repair): apply corrupts the config then fails → must roll back.
        # current_admin_password must match the first provision's admin
        # password to pass the (separate) admin-auth gate and actually reach
        # the rollback path this test exercises.
        result = provision.run_provision(
            _write_request(
                tmp_path, site_name="Broken Attempt",
                current_admin_password="admin-pass",
            ),
            tmp_path / "r2.json",
            resolver=resolver, do_system=False,
            service=_CorruptThenFail(),
        )
        assert result["ok"] is False
        assert result["rolled_back"] is True
        # Config restored byte-for-byte; secrets still intact.
        assert (resolver.config_dir / "config.yaml").read_bytes() == good_config
        assert secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN) == "admin-pass"

    def test_fresh_install_failure_cleans_partial_config(self, isolated):
        resolver, tmp_path = isolated
        result = provision.run_provision(
            _write_request(tmp_path), tmp_path / "result.json",
            resolver=resolver, do_system=False,
            service=_CorruptThenFail(),
        )
        assert result["ok"] is False
        assert result["rolled_back"] is False  # nothing existed to restore
        # Partial write removed — a failed fresh install leaves no config behind.
        assert not (resolver.config_dir / "config.yaml").exists()
        assert not resolver.provisioned_marker_file.exists()

    def test_snapshot_restore_reports_no_existing_when_empty(self, tmp_path):
        target = tmp_path / "config.yaml"
        snap = provision.ConfigSnapshot([target]).capture()  # target absent
        target.write_text("partial", encoding="utf-8")
        assert snap.restore() is False
        assert not target.exists()  # cleaned up

    def test_capture_treats_a_symlink_as_absent(self, tmp_path):
        """/var/lib/hallptz is writable by the hallptz service user itself — a
        compromised process running as that user could plant a symlink there
        before capture() even runs. It must never trust a symlink's target as
        if it were the real captured secret; restore() then just removes
        whatever it finds at that path. See PR #867 review."""
        secret_target = tmp_path / "unrelated.txt"
        secret_target.write_text("do-not-treat-as-a-secret", encoding="utf-8")
        link = tmp_path / "secret.enc"
        _symlink(link, secret_target)

        snap = provision.ConfigSnapshot([link]).capture()
        assert snap.restore() is False  # treated as absent, not "restored"
        assert not link.exists() and not link.is_symlink()  # link removed
        # The symlink's target must never be touched.
        assert secret_target.read_text(encoding="utf-8") == "do-not-treat-as-a-secret"

    def test_restore_never_writes_through_a_planted_symlink(self, tmp_path):
        """A symlink planted at the target path between capture() and
        restore() must not be followed — the write goes to a fresh regular
        file, never through to the symlink's target."""
        target = tmp_path / "secret.enc"
        target.write_bytes(b"good-content")
        snap = provision.ConfigSnapshot([target]).capture()

        secret_target = tmp_path / "other_secret.txt"
        secret_target.write_text("do-not-overwrite", encoding="utf-8")
        target.unlink()
        _symlink(target, secret_target)

        assert snap.restore() is True
        assert secret_target.read_text(encoding="utf-8") == "do-not-overwrite"
        assert not target.is_symlink()
        assert target.read_bytes() == b"good-content"

    def test_restore_reapplies_captured_owner_and_mode(self, tmp_path, monkeypatch):
        """A mid-repair failure can replace a secret's inode (new owner/mode)
        with good content before it gets chowned back to hallptz:hallptz. restore()
        must not just fix the bytes — it must also restore the original
        owner/mode, or a "successful" rollback silently leaves the secret
        unreadable by hallptz-control.service. See PR #867 review."""
        target = tmp_path / "secret.enc"
        target.write_bytes(b"good-content")
        target.chmod(0o600)
        expected_mode = target.stat().st_mode & 0o777  # what capture() will actually see
        snap = provision.ConfigSnapshot([target]).capture()

        # Simulate apply_files replacing the inode (write_text_atomic) with a
        # different owner/mode before a later step fails.
        target.write_bytes(b"corrupt-content")
        target.chmod(0o644)

        # restore() now goes through _safe_write_regular_file, which
        # fchown/fchmod on the fd rather than chown/chmod by path — mock
        # those (Windows also lacks os.fchown/doesn't honour POSIX mode bits
        # at the filesystem level, so asserting real st_mode isn't portable;
        # what matters is that restore() *calls* fchown/fchmod with the
        # captured owner/mode).
        chown_calls = []
        monkeypatch.setattr(
            provision.os, "fchown", lambda fd, u, g: chown_calls.append((u, g)),
            raising=False,  # os.fchown doesn't exist as an attribute on Windows
        )
        chmod_calls = []
        monkeypatch.setattr(
            provision.os, "fchmod", lambda fd, mode: chmod_calls.append(mode)
        )

        assert snap.restore() is True
        assert target.read_bytes() == b"good-content"
        assert len(chown_calls) == 1
        assert len(chmod_calls) == 1 and chmod_calls[0] == expected_mode

    def test_restore_chown_failure_is_swallowed(self, tmp_path, monkeypatch):
        """Not root / no chown on this platform — restore() must still fix bytes."""
        target = tmp_path / "secret.enc"
        target.write_bytes(b"good-content")
        snap = provision.ConfigSnapshot([target]).capture()
        target.write_bytes(b"corrupt-content")

        def _boom(*a):
            raise OSError("not permitted")

        monkeypatch.setattr(provision.os, "fchown", _boom, raising=False)
        assert snap.restore() is True
        assert target.read_bytes() == b"good-content"


def _symlink(link_path, target_path):
    """Create a symlink, skipping the test if the platform/user lacks privilege
    (e.g. Windows without Developer Mode). Real on CI (ubuntu-latest, where an
    unprivileged user can always create symlinks)."""
    try:
        link_path.symlink_to(target_path)
    except OSError as exc:
        pytest.skip(f"platform cannot create symlinks without privilege: {exc}")


def _fifo(path):
    """Create a FIFO at *path*, skipping the test where os.mkfifo is
    unavailable (Windows). Real on CI (ubuntu-latest)."""
    import os
    if not hasattr(os, "mkfifo"):
        pytest.skip("platform has no os.mkfifo (e.g. Windows)")
    os.mkfifo(str(path))


class TestFifoHardening:
    """A FIFO planted at request_path/result_path must not be able to block
    the privileged reader/writer indefinitely — see PR #867 review (the
    reviewer reproduced a real hang with O_NOFOLLOW alone, before O_NONBLOCK
    was added)."""

    def test_request_fifo_is_rejected_without_blocking(self, isolated):
        resolver, tmp_path = isolated
        req = tmp_path / "request.json"
        _fifo(req)

        # No writer will ever open this FIFO — if the implementation regresses
        # to a blocking open, this call hangs and the test times out instead
        # of failing cleanly. That's the exact risk being guarded against.
        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is False

    def test_shred_does_not_overwrite_a_fifo(self, isolated):
        resolver, tmp_path = isolated
        req = tmp_path / "request.json"
        _fifo(req)
        provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        # _shred must not have blocked trying to open the FIFO for writing;
        # reaching this line at all is the assertion. The FIFO is removed.
        assert not req.exists()


class TestSymlinkHardening:
    """/run/hallptz is writable by the unprivileged wizard user, so the privileged
    oneshot must never follow a symlink planted there — see PR #867 review."""

    def test_request_symlink_is_rejected_not_followed(self, isolated):
        resolver, tmp_path = isolated
        secret_target = tmp_path / "secret_target.txt"
        secret_target.write_text("root-only-content", encoding="utf-8")
        req = tmp_path / "request.json"
        _symlink(req, secret_target)

        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert result["ok"] is False
        # O_NOFOLLOW makes the read fail closed (typically ELOOP — "too many
        # levels of symbolic links"); assert the failure mode, not the exact
        # OS error string, which is platform-dependent.
        assert result.get("error", "")
        # The target file must be untouched — no truncate-through-symlink.
        assert secret_target.read_text(encoding="utf-8") == "root-only-content"

    def test_shred_removes_symlink_without_following(self, isolated):
        resolver, tmp_path = isolated
        secret_target = tmp_path / "secret_target.txt"
        secret_target.write_text("root-only-content", encoding="utf-8")
        req = tmp_path / "request.json"
        _symlink(req, secret_target)

        provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False
        )
        assert not req.exists() and not req.is_symlink()  # symlink itself removed
        assert secret_target.read_text(encoding="utf-8") == "root-only-content"

    def test_shred_zeroes_a_regular_file_before_removing_it(self, tmp_path, monkeypatch):
        """Direct unit test of the legitimate (non-attack) path: _shred()'s
        fd-based rewrite (O_NOFOLLOW open, no reopen by name — see PR #867
        review) must still actually zero a real request file's content, not
        just skip writing entirely.

        unlink() is intercepted (instead of asserted post-hoc — the file is
        gone by then) to capture the bytes on disk at the moment just before
        removal, proving the overwrite happened rather than merely that the
        end state looks the same as if it had been skipped."""
        target = tmp_path / "request.json"
        payload = b'{"entry_password": "super-secret"}'
        target.write_bytes(payload)

        captured = {}
        original_unlink = provision.Path.unlink

        def _spy_unlink(self, *a, **kw):
            if str(self) == str(target) and self.exists():
                captured["bytes"] = self.read_bytes()
            return original_unlink(self, *a, **kw)

        monkeypatch.setattr(provision.Path, "unlink", _spy_unlink)
        provision._shred(target)

        assert b"super-secret" not in captured.get("bytes", b"MISSING")
        assert captured["bytes"] == b"\x00" * len(payload)
        assert not target.exists()

    def test_result_write_never_writes_through_a_planted_symlink(self, isolated, tmp_path):
        """A symlink planted at result_path before the write is never followed:
        _write_result unlinks the link itself (unlink() never follows a
        symlink) then creates a fresh regular file — the O_EXCL create is what
        makes a *raced-in* replacement symlink fail closed instead of being
        written through; here (no race) we assert the resulting invariant."""
        resolver, tmp_path = isolated
        secret_target = tmp_path / "other_secret.txt"
        secret_target.write_text("do-not-overwrite", encoding="utf-8")
        result_path = tmp_path / "result.json"
        _symlink(result_path, secret_target)

        provision._write_result(result_path, {"ok": True})

        assert secret_target.read_text(encoding="utf-8") == "do-not-overwrite"
        assert not result_path.is_symlink()
        assert json.loads(result_path.read_text(encoding="utf-8")) == {"ok": True}


class TestSystemSteps:

    def test_plan_includes_user_dirs_and_service(self):
        cmds = provision.plan_system_commands()
        flat = [" ".join(c) for c in cmds]
        assert any("useradd" in c for c in flat)
        assert any("2751" in c for c in flat)  # config dir mode
        assert any("systemctl enable hallptz-control" in c for c in flat)

    def test_apply_system_steps_uses_injected_runner(self):
        recorded = []
        provision.apply_system_steps(runner=lambda cmd: recorded.append(cmd))
        # useradd may be skipped if the dev box happens to have a 'hallptz' user;
        # the directory installs and systemctl calls must always be issued.
        flat = [" ".join(c) for c in recorded]
        assert any("install -d" in c for c in flat)
        assert any("daemon-reload" in c for c in flat)


class TestRestartControlService:
    """hallptz-control.service gates on ConditionPathExists=.../.provisioned, so
    it may have been skipped at an earlier boot and needs an explicit restart
    once the marker is written — systemd doesn't retry on its own. See PR
    #867 review."""

    def test_restarts_control_service_via_injected_runner(self):
        calls = []
        provision._restart_control_service(runner=lambda cmd: calls.append(cmd))
        assert calls == [["systemctl", "restart", "hallptz-control"]]

    def test_restart_failure_is_swallowed(self):
        def _boom(cmd):
            raise OSError("systemctl not found")

        provision._restart_control_service(runner=_boom)  # must not raise

    def test_run_provision_restarts_service_on_success_when_do_system(self, isolated):
        resolver, tmp_path = isolated
        req = _write_request(tmp_path)
        calls = []
        result = provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=True,
            runner=lambda cmd: calls.append(cmd),
        )
        assert result["ok"] is True
        assert ["systemctl", "restart", "hallptz-control"] in calls

    def test_run_provision_skips_restart_when_not_do_system(self, isolated):
        resolver, tmp_path = isolated
        req = _write_request(tmp_path)
        calls = []
        provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False,
            runner=lambda cmd: calls.append(cmd),
        )
        assert calls == []


class TestSafeChown:
    """_safe_chown() is the default chown for the secrets/config handoff to
    the hallptz service user: fd-based (O_NOFOLLOW + fstat + fchown), never
    reopening by name — /var/lib/hallptz is owned hallptz:hallptz and writable by the
    service user itself, so a compromised process running as that user could
    otherwise swap the real secret for a symlink between apply_files()
    writing it and this chown running. See PR #867 review."""

    def test_chowns_a_regular_file_via_fchown(self, tmp_path, monkeypatch):
        target = tmp_path / "secret.enc"
        target.write_text("content", encoding="utf-8")
        calls = []
        monkeypatch.setattr(
            provision.os, "fchown",
            lambda fd, uid, gid: calls.append((uid, gid)),
            raising=False,  # os.fchown doesn't exist as an attribute on Windows
        )
        provision._safe_chown(target, 111, 222)
        assert calls == [(111, 222)]

    def test_never_follows_a_planted_symlink(self, tmp_path, monkeypatch):
        secret_target = tmp_path / "other_secret.txt"
        secret_target.write_text("do-not-touch", encoding="utf-8")
        link = tmp_path / "secret.enc"
        _symlink(link, secret_target)

        calls = []
        monkeypatch.setattr(
            provision.os, "fchown",
            lambda fd, uid, gid: calls.append((uid, gid)),
            raising=False,
        )
        # O_NOFOLLOW makes the open itself fail (ELOOP) — must propagate, not
        # be swallowed here (the caller wraps this in its own try/except).
        with pytest.raises(OSError):
            provision._safe_chown(link, 111, 222)
        assert calls == []  # fchown never reached — the symlink was never opened


class TestChownSecretsToServiceUser:
    """Secrets are written by whichever user runs the oneshot (root once
    HALLPTZ_DATA_DIR is pinned to match hallptz-control.service's dir) — without a
    chown, hallptz-control.service (User=hallptz) could never decrypt them to
    validate a login. resolve_ids/chown are injected so this is testable
    without real pwd/grp or the hallptz system user — see PR #867 review."""

    def test_chowns_both_secrets_present_in_written(self, isolated):
        resolver, tmp_path = isolated
        svc = provision.ProvisioningService()
        answers = ProvisioningAnswers(entry_password="op-pass", admin_password="admin-pass")
        apply = svc.apply_files(answers, resolver=resolver)

        calls = []
        provision._chown_secrets_to_service_user(
            apply.written,
            resolve_ids=lambda: (999, 999),
            chown=lambda path, uid, gid: calls.append((str(path), uid, gid)),
        )
        assert len(calls) == 2
        assert all(uid == 999 and gid == 999 for _, uid, gid in calls)
        chowned_paths = {p for p, _, _ in calls}
        assert str(secret_manager._secret_file(secret_manager.SECRET_ENTRY)) in chowned_paths
        assert str(secret_manager._secret_file(secret_manager.SECRET_ADMIN)) in chowned_paths

    def test_noop_when_ids_unresolvable(self):
        """Non-POSIX platform, or the hallptz user doesn't exist yet — must not raise."""
        calls = []
        provision._chown_secrets_to_service_user(
            ["/var/lib/hallptz/password.enc"],
            resolve_ids=lambda: None,
            chown=lambda *a: calls.append(a),
        )
        assert calls == []

    def test_chown_failure_is_swallowed(self, isolated):
        resolver, tmp_path = isolated
        svc = provision.ProvisioningService()
        apply = svc.apply_files(
            ProvisioningAnswers(entry_password="a", admin_password="b"), resolver=resolver
        )

        def _boom(*a):
            raise OSError("no such operation on this platform")

        # Must not raise — a chown failure should never fail provisioning.
        provision._chown_secrets_to_service_user(
            apply.written, resolve_ids=lambda: (1, 1), chown=_boom
        )

    def test_run_provision_chowns_secrets_when_do_system(self, isolated, monkeypatch):
        resolver, tmp_path = isolated
        calls = []
        monkeypatch.setattr(
            provision, "_chown_secrets_to_service_user",
            lambda written: calls.append(written),
        )
        req = _write_request(tmp_path)
        provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=True,
            runner=lambda cmd: None,
        )
        assert len(calls) == 1

    def test_run_provision_skips_chown_when_not_do_system(self, isolated, monkeypatch):
        resolver, tmp_path = isolated
        calls = []
        monkeypatch.setattr(
            provision, "_chown_secrets_to_service_user",
            lambda written: calls.append(written),
        )
        req = _write_request(tmp_path)
        provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False,
        )
        assert calls == []


class TestChgrpConfigToServiceGroup:
    """apply_files() writes config.yaml via write_text_atomic, which replaces
    the inode outright — losing the installer's root:hallptz ownership, landing
    root:root. hallptz-control.service (User=hallptz, Group=hallptz) could then never
    read its own config.yaml after any successful provision/repair. See PR
    #867 review."""

    def test_chgrps_config_leaving_owner_unchanged(self, isolated):
        resolver, tmp_path = isolated
        config_path = resolver.config_dir / "config.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("site: {}\n", encoding="utf-8")

        calls = []
        provision._chgrp_config_to_service_group(
            config_path,
            resolve_ids=lambda: (999, 999),
            chown=lambda path, uid, gid: calls.append((str(path), uid, gid)),
        )
        assert calls == [(str(config_path), -1, 999)]  # uid=-1 → owner untouched

    def test_noop_when_ids_unresolvable(self):
        """Non-POSIX platform, or the hallptz user doesn't exist yet — must not raise."""
        calls = []
        provision._chgrp_config_to_service_group(
            Path("/etc/hallptz/config.yaml"),
            resolve_ids=lambda: None,
            chown=lambda *a: calls.append(a),
        )
        assert calls == []

    def test_chown_failure_is_swallowed(self):
        def _boom(*a):
            raise OSError("no such operation on this platform")

        # Must not raise — a chgrp failure should never fail provisioning.
        provision._chgrp_config_to_service_group(
            Path("/etc/hallptz/config.yaml"), resolve_ids=lambda: (1, 1), chown=_boom
        )

    def test_run_provision_chgrps_config_when_do_system(self, isolated, monkeypatch):
        resolver, tmp_path = isolated
        calls = []
        monkeypatch.setattr(
            provision, "_chgrp_config_to_service_group",
            lambda config_path: calls.append(config_path),
        )
        req = _write_request(tmp_path)
        provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=True,
            runner=lambda cmd: None,
        )
        assert calls == [resolver.config_dir / "config.yaml"]

    def test_run_provision_skips_chgrp_when_not_do_system(self, isolated, monkeypatch):
        resolver, tmp_path = isolated
        calls = []
        monkeypatch.setattr(
            provision, "_chgrp_config_to_service_group",
            lambda config_path: calls.append(config_path),
        )
        req = _write_request(tmp_path)
        provision.run_provision(
            req, tmp_path / "result.json", resolver=resolver, do_system=False,
        )
        assert calls == []


class TestMainCli:

    def test_main_returns_zero_on_success(self, isolated):
        resolver, tmp_path = isolated
        req = _write_request(tmp_path)
        res = tmp_path / "result.json"
        rc = provision.main(["--request", str(req), "--result", str(res)])
        assert rc == 0
        assert json.loads(res.read_text(encoding="utf-8"))["ok"] is True

    def test_main_returns_one_on_failure(self, isolated):
        resolver, tmp_path = isolated
        req = _write_request(tmp_path, admin_password="")
        res = tmp_path / "result.json"
        rc = provision.main(["--request", str(req), "--result", str(res)])
        assert rc == 1
