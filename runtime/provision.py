#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""runtime/provision.py — privileged provisioning entrypoint.

Run as root by the khptz-provision systemd oneshot when the unprivileged wizard
drops a request file in /run/khptz (tmpfs). The request carries the wizard
answers plus the two plaintext passwords; this module:

  1. reads and validates the request,
  2. writes config.yaml + both encrypted secrets (ProvisioningService),
  3. performs the OS steps (service user, directories, systemd) on Linux,
  4. writes a result file the wizard polls,
  5. shreds the request so the plaintext passwords never persist to the SD card.

Design notes:
  - The request lives only in tmpfs and is shredded here; secrets at rest are
    the encrypted .enc files, never plaintext.
  - plan_system_commands() is pure and testable; the actual OS mutation is the
    only part that needs a real Pi (CI/dev keep do_system=False).
  - Re-running is safe: ProvisioningService.apply_files is idempotent and the
    OS commands are guarded by existence checks in apply_system_steps.
"""

from __future__ import annotations

import json
import os
import platform
import stat
from dataclasses import asdict
from pathlib import Path
from typing import Callable, List, Optional

from application.provisioning_service import (
    CameraAnswer,
    ProvisioningAnswers,
    ProvisioningIssue,
    ProvisioningService,
)
from runtime.path_resolver import RuntimePathResolver

SERVICE_USER = "khptz"
SERVICE_NAME = "khptz-control"


# ── Request (de)serialisation ─────────────────────────────────────────────────

def answers_to_dict(answers: ProvisioningAnswers) -> dict:
    return asdict(answers)


def answers_from_dict(data: dict) -> ProvisioningAnswers:
    """Rebuild ProvisioningAnswers from a request mapping (tolerant of missing keys)."""
    base = ProvisioningAnswers()
    cams_raw = data.get("cameras")
    cameras = base.cameras
    if isinstance(cams_raw, list):
        cameras = [
            CameraAnswer(
                id=str(c.get("id", "")),
                role=str(c.get("role", "")),
                ip=str(c.get("ip", "")),
                visca_id=str(c.get("visca_id", "")),
                name=str(c.get("name", "")),
            )
            for c in cams_raw
            if isinstance(c, dict)
        ]
    return ProvisioningAnswers(
        site_name=str(data.get("site_name", base.site_name)),
        site_contact=str(data.get("site_contact", base.site_contact)),
        installation_id=str(data.get("installation_id", base.installation_id)),
        cameras=cameras,
        atem_enabled=bool(data.get("atem_enabled", base.atem_enabled)),
        atem_ip=str(data.get("atem_ip", base.atem_ip)),
        network_profile=str(data.get("network_profile", base.network_profile)),
        entry_password=str(data.get("entry_password", "")),
        admin_password=str(data.get("admin_password", "")),
        current_admin_password=str(data.get("current_admin_password", "")),
    )


def _read_request_safely(path: Path) -> str:
    """Read *path* without ever following a symlink, closing the TOCTOU window
    a separate is_symlink()-then-read_text() would leave open.

    /run/khptz is writable by the unprivileged wizard user, who could otherwise
    swap in a symlink between a check and a later read. O_NOFOLLOW makes the
    open itself fail (ELOOP) on a symlink — there is no gap to race — and the
    fstat check additionally refuses any non-regular file (fifo, device, ...)
    that could otherwise be planted at that path to stall or misdirect this
    privileged reader. O_NONBLOCK is required for that fstat check to ever be
    reached: opening a FIFO for reading blocks until a writer opens it, before
    fstat() gets a chance to reject it — O_NONBLOCK makes the open return
    immediately instead. It has no effect on how a regular file reads once
    fstat confirms that's what this is.
    """
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    fd = os.open(str(path), flags)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"{path} is not a regular file — refusing to read it")
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            fd = -1  # fdopen now owns the fd — avoid the double-close below
            return fh.read()
    finally:
        if fd >= 0:
            os.close(fd)


def _shred(path: Path) -> None:
    """Best-effort secure delete: overwrite then unlink. Request lives in tmpfs.

    Only overwrites a regular file, verified from the SAME open file
    descriptor it then writes through — an earlier version checked with
    os.lstat() and then reopened by name via open(path, "wb"), which left a
    TOCTOU window: /run/khptz is writable by the unprivileged wizard user, who
    could swap the path to a symlink between the check and the reopen. A
    single O_NOFOLLOW|O_NONBLOCK open (no O_CREAT — the file must already
    exist) closes that window the same way _read_request_safely does for
    reads: O_NOFOLLOW makes the open itself fail on a symlink, and
    O_NONBLOCK stops a planted FIFO from blocking the open indefinitely.
    unlink() never follows a symlink either way, so the link/file itself is
    always removed regardless of what the open above found.
    """
    flags = (
        os.O_WRONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(str(path), flags)
    except OSError:
        fd = -1
    if fd >= 0:
        try:
            st = os.fstat(fd)
            if stat.S_ISREG(st.st_mode):
                os.write(fd, b"\x00" * max(st.st_size, 1))
                os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _write_result(result_path: Path, result: dict) -> None:
    """Write result.json, refusing to follow a symlink at that path.

    Same /run/khptz symlink concern as _shred: unlink whatever currently sits
    at result_path (safe — unlink never follows a symlink) immediately before
    an exclusive create, so a symlink raced back into that window makes this
    fail rather than silently overwrite whatever it points at.
    """
    result_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result_path.unlink()
    except FileNotFoundError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(str(result_path), flags, 0o644)
    try:
        os.write(fd, json.dumps(result).encode("utf-8"))
    finally:
        os.close(fd)


def _resolve_service_user_ids() -> "Optional[tuple[int, int]]":
    """Look up the khptz service user's (uid, gid); None if unavailable
    (non-POSIX platform, or the user does not exist yet — CI, dev, tests)."""
    try:
        import grp
        import pwd

        return pwd.getpwnam(SERVICE_USER).pw_uid, grp.getgrnam(SERVICE_USER).gr_gid
    except (ImportError, KeyError):
        return None


def _safe_chown(path: Path, uid: int, gid: int) -> None:
    """Default chown for the service-user handoff: fd-based, never follows a
    symlink.

    /var/lib/khptz is owned khptz:khptz 0750 — the khptz-control.service process
    itself can write there. A compromised process running as that user could
    swap the just-written secret for a symlink in the window between
    apply_files() writing it and this chown running; a naive
    os.chown(path, ...) follows symlinks by name and would hand khptz
    ownership of whatever the link points at. O_NOFOLLOW makes the open
    itself fail on a symlink, and fchown operates on the already-open,
    already-verified-regular fd — there is no reopen-by-name to race.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(str(path), flags)
    try:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            os.fchown(fd, uid, gid)
    finally:
        os.close(fd)


def _chown_secrets_to_service_user(
    written: List[str],
    *,
    resolve_ids: Callable[[], "Optional[tuple[int, int]]"] = _resolve_service_user_ids,
    chown: Optional[Callable[[Path, int, int], None]] = None,
) -> None:
    """Chown the two password secrets to the khptz service user (best-effort).

    apply_files() writes secrets 0600 as whichever user runs this oneshot —
    root, since KHPTZ_DATA_DIR now matches khptz-control.service's secrets dir.
    Without this, the secrets land root:root and khptz-control.service (which
    runs as User=khptz) could never decrypt them to validate a login. Never
    raises — a failure here should not fail provisioning, `khptz doctor`
    surfaces it. ``resolve_ids``/``chown`` are injectable (same pattern as
    ``apply_system_steps``'s ``runner``) since pwd/grp are POSIX-only and the
    khptz user does not exist outside a real Pi install. Default ``chown`` is
    the symlink-safe ``_safe_chown``, not a raw ``os.chown`` by path.
    """
    ids = resolve_ids()
    if ids is None:
        return
    uid, gid = ids
    if chown is None:
        chown = _safe_chown
    from runtime import secret_manager

    for name in (secret_manager.SECRET_ENTRY, secret_manager.SECRET_ADMIN):
        path = secret_manager._secret_file(name)
        if str(path) in written:
            try:
                chown(path, uid, gid)
            except OSError:
                pass


def _chgrp_config_to_service_group(
    config_path: Path,
    *,
    resolve_ids: Callable[[], "Optional[tuple[int, int]]"] = _resolve_service_user_ids,
    chown: Optional[Callable[[Path, int, int], None]] = None,
) -> None:
    """Fix config.yaml's group to khptz after apply_files() replaces its inode.

    apply_files() writes config.yaml via write_text_atomic, which replaces the
    inode outright — losing the installer's original root:khptz ownership
    every time this privileged oneshot runs, landing it root:root instead
    (whatever root's primary group happens to be). Left that way, mode 0640
    gives group-read, but the "root" group does not include khptz —
    khptz-control.service (User=khptz, Group=khptz) could no longer read its own
    config after any successful provision/repair. Owner stays root (uid left
    unchanged, matching the installer's convention); only the group changes.
    Never raises — matches _chown_secrets_to_service_user's best-effort
    pattern; `khptz doctor` surfaces a failure here. Default ``chown`` is the
    symlink-safe ``_safe_chown`` (see its docstring) — config_dir's own
    permissions (root:khptz, no group/other write) already rule out the
    same swap risk the secrets face, but staying consistent costs nothing.
    """
    ids = resolve_ids()
    if ids is None:
        return
    _, gid = ids
    if chown is None:
        chown = _safe_chown
    try:
        chown(config_path, -1, gid)
    except OSError:
        pass


# ── Snapshot / rollback (repair safety) ───────────────────────────────────────

def _provisioned_files(resolver: RuntimePathResolver) -> List[Path]:
    """The files a re-provision overwrites — the snapshot/rollback targets."""
    from runtime import secret_manager
    return [
        resolver.config_dir / "config.yaml",
        secret_manager._secret_file(secret_manager.SECRET_ENTRY),
        secret_manager._secret_file(secret_manager.SECRET_ADMIN),
    ]


def _safe_capture_file(path: Path) -> "Optional[tuple[bytes, int, int, int]]":
    """Read *path*'s bytes + owner/group/mode via a single safe fd.

    Refuses to follow a symlink (O_NOFOLLOW) and refuses anything but a
    regular file — /var/lib/khptz is writable by the khptz service user itself
    (khptz-control.service), so a compromised process running as that user
    could plant a symlink there before this snapshot is even taken. Returns
    None (treated the same as "absent") for a missing path, a symlink, or any
    other non-regular file — restore() then just unlinks whatever it finds
    there rather than trusting a symlink's target as if it were the real
    captured secret.
    """
    flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(str(path), flags)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            return None
        chunks = []
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), st.st_uid, st.st_gid, st.st_mode & 0o777
    finally:
        os.close(fd)


def _safe_write_regular_file(path: Path, data: bytes, uid: int, gid: int, mode: int) -> None:
    """Write *data* to *path* as a fresh regular file; chown/chmod happen on
    that same fd, never by reopening the path afterward.

    Same /var/lib/khptz concern as _safe_capture_file: unlink whatever
    currently sits at *path* (safe — unlink never follows a symlink)
    immediately before an O_NOFOLLOW|O_EXCL create, so a symlink raced back
    into that window fails the write instead of writing through it. Never
    raises — restore() is itself a best-effort rollback.
    """
    try:
        path.unlink()
    except OSError:
        pass  # missing, or something odd there — the create below reports it
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        fd = os.open(str(path), flags, 0o600)
    except OSError:
        return
    try:
        written = 0
        mv = memoryview(data)
        while written < len(mv):
            written += os.write(fd, mv[written:])
        try:
            os.fchown(fd, uid, gid)
        except (AttributeError, OSError):
            pass  # os.fchown doesn't exist on Windows; not root — best-effort
        try:
            os.fchmod(fd, mode)
        except OSError:
            pass
    finally:
        os.close(fd)


class ConfigSnapshot:
    """In-memory backup of the files a re-provision overwrites, for rollback.

    ``capture`` records each target's current bytes plus owner/group/mode (or
    None if absent). ``restore`` puts existing files back byte-for-byte *and*
    with their original ownership/permissions, and deletes any file that was
    absent before — so a failed re-provision never leaves the install with a
    half-written config or mismatched secrets. On a fresh install there is
    nothing to restore, only cleanup of partial writes.

    The ownership restore matters specifically for secrets: apply_files()
    writes them via write_text_atomic, which replaces the inode outright, so
    a mid-repair failure after that replace but before
    _chown_secrets_to_service_user() runs would otherwise leave a
    content-correct but root:root-owned secret behind after "successful"
    rollback — unreadable by khptz-control.service (User=khptz) despite the
    result saying rolled_back=True.

    Both capture and restore go through the fd-based _safe_capture_file /
    _safe_write_regular_file helpers rather than Path.read_bytes()/
    write_bytes()/os.chown() by name — /var/lib/khptz is writable by the khptz
    service user, so a compromised process running as that user could swap a
    secret for a symlink between capture() and restore() otherwise.
    """

    def __init__(self, files: List[Path]) -> None:
        self._targets = files
        self._saved: dict = {}

    def capture(self) -> "ConfigSnapshot":
        self._saved = {p: _safe_capture_file(p) for p in self._targets}
        return self

    def restore(self) -> bool:
        """Roll back to the captured state; True if pre-existing files were restored."""
        restored_existing = False
        for path, entry in self._saved.items():
            if entry is None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                data, uid, gid, mode = entry
                path.parent.mkdir(parents=True, exist_ok=True)
                _safe_write_regular_file(path, data, uid, gid, mode)
                restored_existing = True
        return restored_existing


# ── OS step planning (pure) ───────────────────────────────────────────────────

def plan_system_commands(resolver: Optional[RuntimePathResolver] = None) -> List[List[str]]:
    """Return the root commands that bring the OS layout into place.

    Pure and order-significant: create the user, then the directories with their
    ownership/modes, then reload + enable the service. Executed by
    apply_system_steps on a real Pi; asserted directly in tests.
    """
    r = resolver or RuntimePathResolver()
    cfg, data = str(r.config_dir), str(r.data_dir)
    log, backup = str(r.log_dir), str(r.backup_dir)

    # Who owns the GUI decides two things here (#885). This runs as root from
    # the wizard's provisioning channel on EVERY install, so getting it wrong
    # silently re-arms a second launcher on a session-owned appliance.
    from runtime.install_state import gui_is_session_owned

    session_owned = gui_is_session_owned(r)

    # Runtime directories: 2770 when the desktop GUI shares them with the
    # service through the khptz group, 0750 when only the service writes. Using
    # 0750 unconditionally would undo what install.sh --gui-mode user set and
    # leave the GUI unable to write presets, seats or logs.
    runtime_mode = "2770" if session_owned else "0750"

    commands: List[List[str]] = [
        ["useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin", SERVICE_USER],
        # config dir: root:khptz, setgid + others-traverse (2751) so the desktop
        # session can stat the .provisioned marker without reading secrets.
        ["install", "-d", "-m", "2751", "-o", "root", "-g", SERVICE_USER, cfg],
        ["install", "-d", "-m", runtime_mode, "-o", SERVICE_USER, "-g", SERVICE_USER, data],
        ["install", "-d", "-m", runtime_mode, "-o", SERVICE_USER, "-g", SERVICE_USER, log],
        ["install", "-d", "-m", runtime_mode, "-o", SERVICE_USER, "-g", SERVICE_USER, backup],
        ["systemctl", "daemon-reload"],
    ]

    # Enabling the system service on a session-owned install is the
    # two-competing-GUIs bug: install.sh deliberately disabled it, and the
    # desktop session already starts khptz-gui.service at login.
    if not session_owned:
        commands.append(["systemctl", "enable", SERVICE_NAME])

    return commands


def apply_system_steps(
    resolver: Optional[RuntimePathResolver] = None,
    runner: Callable[[List[str]], object] = None,
) -> None:
    """Run the OS steps. Only meaningful as root on Linux.

    `runner` is injectable for tests (records commands without executing). The
    default runner uses subprocess.run with check=True. `useradd` is tolerated
    if the user already exists (idempotent re-provision).
    """
    if runner is None:
        import subprocess

        def runner(cmd):  # noqa: ANN001
            return subprocess.run(cmd, check=True)

    for cmd in plan_system_commands(resolver):
        if cmd[:1] == ["useradd"] and _user_exists(SERVICE_USER):
            continue
        runner(cmd)


def _restart_control_service(runner: Callable[[List[str]], object] = None) -> None:
    """Start/restart khptz-control.service once provisioning succeeds.

    khptz-control.service gates on ConditionPathExists=.../.provisioned, so if
    it attempted to start earlier (before the marker existed, e.g. at boot)
    systemd skipped it and will NOT retry on its own now that the marker
    exists — nothing else pokes it. This also picks up fresh config/secrets
    for an install that was already running on stale/starter values from a
    prior partial setup. Best-effort: a restart failure here does not roll
    back an otherwise-successful provisioning result — `khptz doctor`/`khptz
    status` already surface the service's actual running state.
    """
    # On a session-owned install (#885) khptz-control is deliberately disabled
    # and khptz-gui.service is started by the desktop session at login.
    # Restarting the system service here would not merely arm a second
    # launcher — it would put a second full-screen GUI on the cameras
    # immediately, while the operator is still finishing the wizard.
    from runtime.install_state import gui_is_session_owned

    if gui_is_session_owned():
        return

    if runner is None:
        import subprocess

        def runner(cmd):  # noqa: ANN001
            return subprocess.run(cmd, check=True)

    try:
        runner(["systemctl", "restart", SERVICE_NAME])
    except Exception:  # noqa: BLE001 — best-effort, never fails provisioning
        pass


def _user_exists(name: str) -> bool:
    try:
        import pwd

        pwd.getpwnam(name)
        return True
    except (KeyError, ImportError):
        return False


def is_privileged_linux() -> bool:
    """True only on Linux running as root — where OS mutation is allowed."""
    return platform.system() == "Linux" and hasattr(os, "geteuid") and os.geteuid() == 0


# ── Entry point ───────────────────────────────────────────────────────────────

def run_provision(
    request_path: Path,
    result_path: Path,
    *,
    resolver: Optional[RuntimePathResolver] = None,
    service: Optional[ProvisioningService] = None,
    do_system: Optional[bool] = None,
    runner: Callable[[List[str]], object] = None,
) -> dict:
    """Provision from a request file; always writes a result and shreds the request.

    Returns the result dict (also written to result_path). `do_system` defaults
    to is_privileged_linux(); pass False in tests/dev to skip OS mutation.
    """
    r = resolver or RuntimePathResolver()
    svc = service or ProvisioningService()
    if do_system is None:
        do_system = is_privileged_linux()

    result: dict
    try:
        # _read_request_safely refuses to follow a symlink (O_NOFOLLOW) and
        # refuses anything but a regular file — /run/khptz is writable by the
        # unprivileged wizard user. Any failure here is treated the same as a
        # corrupt request by the broad except below.
        data = json.loads(_read_request_safely(request_path))
        answers = answers_from_dict(data)

        issues = svc.validate(answers)
        if not issues and r.provisioned_marker_file.exists():
            # An already-provisioned install has real settings to protect.
            # /run/khptz is writable by the unprivileged wizard user, so a raw
            # request dropped there directly — bypassing the wizard's own
            # AdminAuthPage entirely — must not be enough on its own to
            # reconfigure or reset both passwords. Checked HERE, not in the
            # wizard's UI process: this privileged oneshot is the only
            # context that reliably resolves/decrypts the khptz:khptz-owned
            # secrets (KHPTZ_DATA_DIR is pinned for this unit; a
            # desktop-launched `khptz setup` process is not).
            from application.authentication import verify_admin
            if not verify_admin(answers.current_admin_password):
                issues = [ProvisioningIssue(
                    "current_admin_password",
                    "Incorrect administrator password.",
                    "Re-enter the current administrator password to reconfigure this install.",
                )]
        if issues:
            result = {
                "ok": False,
                "issues": [
                    {"field": i.field_path, "message": i.message} for i in issues
                ],
            }
        else:
            # Snapshot the files this run overwrites so a mid-apply failure on a
            # repair rolls back to the previous working config instead of leaving
            # a broken install. On a fresh install this only cleans partial writes.
            snapshot = ConfigSnapshot(_provisioned_files(r)).capture()
            try:
                if do_system:
                    apply_system_steps(r, runner=runner)
                apply = svc.apply_files(answers, resolver=r)
                if do_system:
                    _chown_secrets_to_service_user(apply.written)
                    _chgrp_config_to_service_group(r.config_dir / "config.yaml")
                r.provisioned_marker_file.parent.mkdir(parents=True, exist_ok=True)
                r.provisioned_marker_file.write_text("ok\n", encoding="ascii")
                if do_system:
                    _restart_control_service(runner)
                result = {"ok": True, "written": apply.written}
            except Exception as exc:  # noqa: BLE001 — roll back, then report
                rolled_back = snapshot.restore()
                result = {"ok": False, "error": str(exc), "rolled_back": rolled_back}
    except Exception as exc:  # noqa: BLE001 — must always produce a result
        result = {"ok": False, "error": str(exc)}
    finally:
        _shred(request_path)

    _write_result(result_path, result)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    """CLI used by the khptz-provision systemd oneshot. Returns 0 on success."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="khptz-provision",
        description="Apply a setup provisioning request (run as root by systemd).",
    )
    parser.add_argument("--request", required=True, type=Path,
                        help="Path to the request JSON (wizard answers + passwords)")
    parser.add_argument("--result", required=True, type=Path,
                        help="Path to write the result JSON")
    args = parser.parse_args(argv)

    result = run_provision(args.request, args.result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
