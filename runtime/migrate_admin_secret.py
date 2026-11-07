"""Explicit privileged reset for installations whose admin secret lived in data.

No automatic migration trusts a credential from a GUI-writable directory.
Run from the installed code as root, with the GUI/service stopped. The operator
password is neither read nor changed. No password is accepted on the command line.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path
import pwd
import stat

from core.atomic_write import write_text_atomic
from runtime import secret_manager


def reset_admin(
    password: str, confirmation: str, *, data_dir: Path, secret_dir: Path, uid: int, gid: int
) -> None:
    """Called only by the privileged CLI; paths/IDs injectable for isolated tests."""
    if not password or password != confirmation:
        raise ValueError("New administrator passwords must be nonempty and match")
    info = secret_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
        raise ValueError("Administrator directory must be a real, non-shared directory")
    salt = os.urandom(16)
    encrypted = secret_manager._xor_stream(password.encode(), secret_manager._derive_key(salt))
    dest = secret_dir / "admin.enc"
    write_text_atomic(dest, salt.hex() + ":" + encrypted.hex(), encoding="ascii", mode=0o600)
    os.chown(dest, uid, gid, follow_symlinks=False)
    # Only remove the legacy path after the new credential has been persisted.
    # Unlink removes a planted symlink itself, never its target.
    (data_dir / "admin.enc").unlink(missing_ok=True)


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("Run as root from the installed code with GUI/service stopped")
    dest = Path("/etc/khptz/secrets")
    # Do not create or follow a caller-selected directory in privileged mode.
    info = dest.lstat()
    if info.st_uid != 0 or not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
        raise SystemExit("Prepare /etc/khptz/secrets as root-owned 0750 first")
    account = pwd.getpwnam("khptz")
    password = getpass.getpass("New administrator password: ")
    confirmation = getpass.getpass("Repeat new administrator password: ")
    reset_admin(
        password,
        confirmation,
        data_dir=Path("/var/lib/khptz"),
        secret_dir=dest,
        uid=account.pw_uid,
        gid=account.pw_gid,
    )
    print("Administrator credential reset in protected store. Operator password unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
