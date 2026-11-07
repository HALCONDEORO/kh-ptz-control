"""Fail-closed administrator identity and restore safety regressions."""

from unittest.mock import Mock
import pytest
from application import authentication as auth
from application.restore_service import RestoreError
from tests.test_restore_service import _make_services, _make_zip
from runtime import secret_manager


def test_missing_admin_never_uses_operator(monkeypatch):
    monkeypatch.setattr(secret_manager, "secret_file_exists", lambda name: False)
    operator = Mock(return_value=True)
    monkeypatch.setattr(auth, "verify_entry", operator)
    assert not auth.verify_admin("fixture-only")
    operator.assert_not_called()


def test_pre_restore_backup_failure_preserves_current_data(tmp_path, monkeypatch):
    _, svc = _make_services(tmp_path)
    target = svc._data_dir / "seat_names.json"
    target.write_text("current")
    archive = _make_zip(tmp_path, {"seat_names.json": "replacement"})
    monkeypatch.setattr(
        "application.backup_service.BackupService.create_backup",
        Mock(side_effect=OSError("disk full")),
    )
    with pytest.raises(RestoreError, match="safety backup"):
        svc._restore_inner(archive)
    assert target.read_text() == "current"


def test_production_admin_is_not_in_shared_data(monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(secret_manager, "_CONFIG_DIR", Path("/var/lib/khptz"))
    assert secret_manager._secret_file(secret_manager.SECRET_ADMIN) == Path(
        "/etc/khptz/secrets/admin.enc"
    )


def test_user_gui_admin_denied_even_for_correct_secret(monkeypatch):
    monkeypatch.setenv("KHPTZ_GUI_MODE", "user")
    decrypt = Mock(return_value="fixture-only")
    monkeypatch.setattr(secret_manager, "decrypt_secret", decrypt)
    assert not auth.verify_admin("fixture-only")
    decrypt.assert_not_called()


def test_installer_parent_protected_and_gui_still_shares_data():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    source = (root / "runtime/installer/install.sh").read_text()
    assert 'install -d -m 0750 -o root -g "${APP_USER}" "${ADMIN_SECRET_DIR}"' in source
    assert 'ADMIN_SECRET_DIR="${CONFIG_DIR}/secrets"' in source
    assert 'chmod 2770 "${DATA_DIR}"' in source
    assert source.index("Legacy admin secret requires") < source.index("Creating directories")
    assert (
        "Environment=KHPTZ_GUI_MODE=user"
        in (root / "runtime/systemd/user/khptz-gui.service").read_text()
    )


def test_explicit_reset_does_not_copy_operator_or_legacy(tmp_path, monkeypatch):
    import os
    from runtime.migrate_admin_secret import reset_admin

    data = tmp_path / "data"
    data.mkdir(mode=0o770)
    dest = tmp_path / "secrets"
    dest.mkdir(mode=0o750)
    (data / "admin.enc").write_text("untrusted legacy fixture")
    (data / "password.enc").write_text("operator untouched")
    reset_admin(
        "new-admin-fixture",
        "new-admin-fixture",
        data_dir=data,
        secret_dir=dest,
        uid=os.getuid(),
        gid=os.getgid(),
    )
    assert not (data / "admin.enc").exists()
    assert (data / "password.enc").read_text() == "operator untouched"
    assert (dest / "admin.enc").stat().st_mode & 0o777 == 0o600
    monkeypatch.setattr(secret_manager, "_CONFIG_DIR", dest)
    assert secret_manager.decrypt_secret(secret_manager.SECRET_ADMIN) == "new-admin-fixture"


def test_reset_rejects_group_writable_parent(tmp_path):
    import os
    from runtime.migrate_admin_secret import reset_admin

    dest = tmp_path / "secrets"
    dest.mkdir()
    dest.chmod(0o770)
    with pytest.raises(ValueError, match="non-shared"):
        reset_admin(
            "fixture",
            "fixture",
            data_dir=tmp_path,
            secret_dir=dest,
            uid=os.getuid(),
            gid=os.getgid(),
        )
    assert not (dest / "admin.enc").exists()


def test_unlink_existing_admin_does_not_promote_operator(tmp_path, monkeypatch):
    monkeypatch.setattr(secret_manager, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(secret_manager, "_ENC_FILE", tmp_path / "password.enc")
    secret_manager.encrypt_secret(secret_manager.SECRET_ENTRY, "operator-fixture")
    secret_manager.encrypt_secret(secret_manager.SECRET_ADMIN, "admin-fixture")
    assert not auth.verify_admin("operator-fixture")
    (tmp_path / "admin.enc").unlink()
    assert not auth.verify_admin("operator-fixture")


def test_missing_backup_result_aborts_before_write(tmp_path, monkeypatch):
    _, svc = _make_services(tmp_path)
    target = svc._data_dir / "seat_names.json"
    target.write_text("current")
    archive = _make_zip(tmp_path, {"seat_names.json": "replacement"})
    monkeypatch.setattr(svc, "_create_pre_restore_backup", lambda: None)
    with pytest.raises(RestoreError, match="safety backup"):
        svc._restore_inner(archive)
    assert target.read_text() == "current"


def test_failed_reset_leaves_legacy_untouched(tmp_path, monkeypatch):
    import os
    from runtime import migrate_admin_secret as migration

    dest = tmp_path / "secrets"
    dest.mkdir(mode=0o750)
    legacy = tmp_path / "admin.enc"
    legacy.write_text("legacy fixture")
    monkeypatch.setattr(
        migration, "write_text_atomic", Mock(side_effect=OSError("fixture disk full"))
    )
    with pytest.raises(OSError):
        migration.reset_admin(
            "new", "new", data_dir=tmp_path, secret_dir=dest, uid=os.getuid(), gid=os.getgid()
        )
    assert legacy.read_text() == "legacy fixture"
    assert not (dest / "admin.enc").exists()


def test_unreadable_admin_parent_denies(monkeypatch):
    monkeypatch.setattr(
        secret_manager, "decrypt_secret", Mock(side_effect=PermissionError("parent inaccessible"))
    )
    assert not auth.verify_admin("fixture")
