# Runtime Path, Ownership and Legacy Data Migration Contract

Issue: #530.
Parent: #455.

This document is the canonical source of truth for Hall PTZ Control path layout,
ownership, permissions and the migration path from legacy locations.
It must be reviewed before any implementation that writes or migrates customer
config, passwords, layouts, logs or backups.

---

## Canonical path layout (Raspberry Pi service install)

```text
/opt/hallptz/                  Application code — installed by the HALLPTZ installer.
                            Read-only in normal service use.
                            Owned by root:root, mode 0755.
                            No customer or site data lives here.

/etc/hallptz/                  Customer and site configuration.
                            Written once at provisioning; updated by admin/support only.
                            Owned by root:hallptz, mode 2750 (setgid so new files inherit group).
                            Examples: config.yaml, room_layout.json, seat_names.json
                            Also holds two installer-owned control files:
                              .provisioned      sentinel written by the setup wizard's
                                                privileged oneshot; hallptz-control.service
                                                gates on it (ConditionPathExists).
                              install-state.env installed ref, previous ref, source
                                                checkout and wizard user. Lives here —
                                                not in /opt/hallptz — because the install
                                                dir is replaced wholesale on every
                                                deploy. rollback.sh reads it to know
                                                what to re-deploy and from where.

/run/hallptz/                  Volatile setup-wizard provisioning channel (tmpfs).
                            Created 0750 <desktop-user>:root by tmpfiles.d so only the
                            wizard's session user can drop request.json. Never holds
                            data at rest: the privileged oneshot shreds the request
                            after applying it. Recreated empty on every boot.

/var/lib/hallptz/              Persistent customer runtime data.
                            Written at runtime by the hallptz service.
                            Owned by hallptz:hallptz, mode 0750.
                            Examples: chairman_presets.json, session.active,
                                      change_history.json, atem_mapping.json,
                                      known_good state

                            atem_mapping.json lives HERE, not in /etc/hallptz.
                            It is rewritten at runtime by the operator from the
                            running app, and /etc/hallptz is not writable by the
                            service - every save failed with EACCES and was
                            swallowed as a log warning, so the setting silently
                            reverted on the next restart. The pre-move location
                            is a read-migrate source only; it is never written
                            and never deleted.

/var/log/hallptz/              Production log files.
                            Written at runtime by the hallptz service and logrotate.
                            Owned by hallptz:hallptz, mode 0750.
                            Examples: hallptz.log, hallptz.log.1, ...

/var/backups/hallptz/          Local backup output.
                            Written by hallptz backup commands and the installer.
                            Owned by hallptz:hallptz, mode 0750.
                            Examples: backup-2026-05-12T14:30:00.zip

~/.config/hallptz/        Legacy compatibility location (existing installs only).
                            Read-migration source — never written by new code.
                            Preserved as-is until a deliberate migration command runs.
                            See Legacy compatibility below.
```

### Service user

```text
User:   hallptz
Group:  hallptz
Shell:  /usr/sbin/nologin
Home:   /var/lib/hallptz
```

The service user must not be root.
The service process must not own /opt/hallptz/ files.

---

## Schedule file

`schedule.json` is site config (provisioned, not changed at runtime).
Its canonical location is `/etc/hallptz/schedule.json`.

For the current MVP, `schedule.json` lives in `~/.config/hallptz/` via `data_paths.py`.
The migration to `/etc/hallptz/` is a follow-up implementation task.

---

## Environment variable overrides

The following overrides are supported for development, demo, test and support use.
They must never appear in customer systemd unit files without explicit documentation.

| Variable | Overrides | Permitted uses |
|---|---|---|
| `HALLPTZ_DATA_DIR` | `CONFIG_DIR` (all customer data paths) | tests, demo, support |
| `HALLPTZ_CONFIG_DIR` | `/etc/hallptz/` equivalent | tests, support |
| `HALLPTZ_LOG_DIR` | `/var/log/hallptz/` equivalent | tests, support |
| `HALLPTZ_BACKUP_DIR` | `/var/backups/hallptz/` equivalent | tests |

Rules:

```text
All override variables must be validated at startup — relative paths are rejected.
Override values must not be writable by the hallptz service user in production.
hallptz doctor must report which path overrides are active.
Tests must use temporary directories, not the live service directories.
```

---

## Which paths are read-only app code versus writable customer data

```text
Read-only (app code, never written at runtime):
  /opt/hallptz/
  source tree when running from a git checkout (development only)

Writable by hallptz service:
  /var/lib/hallptz/        all customer runtime state
  /var/log/hallptz/        log files
  /var/backups/hallptz/    local backups

Writable by admin/installer only (not by the running service):
  /etc/hallptz/            site configuration

Written once at provisioning; not changed by the running service without
explicit admin/support command.
```

---

## What happens when launched outside the repository CWD

```text
Running from a git checkout (development):
  CONFIG_DIR defaults to ~/.config/hallptz/ (HALLPTZ_DATA_DIR override available).
  Logs go to stderr and/or a local log file.
  No /etc, /var/lib, /var/log paths are required.

Running from a systemd service install:
  CONFIG_DIR and all paths must resolve to the canonical locations above.
  CWD is irrelevant — all paths are absolute and set by the installer.

Running as a demo or test:
  All paths must be overridden via environment variables to use temporary directories.
```

---

## Legacy compatibility

### Current legacy location

```text
~/.config/hallptz/
```

Data files currently living there:

```text
chairman_presets.json
seat_names.json
schedule.json
room_layout.json
change_history.json
session.active
```

### Behaviour contract

```text
Read-migrate: if a file exists at the legacy location and not at the canonical
location, copy it to the canonical location on first startup.

Do not delete legacy files: the migration copy must not remove the legacy original.

Reset legacy stubs: after a successful copy, write a safe empty/default stub to
the legacy location to prevent confusion. The active file is always the canonical one.

Do not write back to legacy: after migration, new code must write only to canonical paths.

Preserve on reinstall: the legacy location survives git pull / reinstall.
No migration must ever delete ~/.config/hallptz/ unless an explicit
support/cleanup command is used and the customer has confirmed backup.
```

### Current state

`data_paths.py` implements the legacy read-migration for:

```text
chairman_presets.json
seat_names.json
schedule.json
```

`HALLPTZ_DATA_DIR` overrides the target directory.
This is the current working compatibility layer for existing installs.

Migration to `/etc/hallptz/` and `/var/lib/hallptz/` is a follow-up implementation task.

---

## Migration order from legacy to canonical paths

The migration must happen in this order to avoid data loss or service interruption:

```text
1. Install the new service user (hallptz:hallptz).
2. Create canonical directories with correct ownership and permissions.
3. Run read-migration for each file:
     a. If file exists at legacy path and not at canonical path: copy.
     b. If file exists at both: log a warning, use canonical, reset legacy stub.
     c. If file exists only at canonical: no action needed.
4. Validate that canonical files parse correctly.
5. Reset legacy stubs.
6. Update systemd unit to use the service user and canonical paths.
7. Restart the service.
8. Confirm hallptz doctor passes.
9. Confirm backup/restore uses canonical paths.
```

### What must not happen during migration

```text
No deletion of ~/.config/hallptz/ without explicit backup and confirmation.
No overwriting canonical files with legacy data if canonical is newer.
No migration while a live event session (session.active) is set.
No migration that changes /etc/hallptz/ config without admin confirmation.
```

---

## Rollback plan if migration fails

```text
Step 1: Stop the hallptz service.
Step 2: Restore legacy location from .bak files if the migration wrote any.
Step 3: Revert the systemd unit to the previous service user and paths.
Step 4: Restart the service pointing at ~/.config/hallptz/.
Step 5: Run hallptz doctor to confirm the legacy path is readable.
Step 6: File a support incident and preserve logs before any retry.
```

The installer must create `.bak` copies of each file before overwriting or moving it.
The rollback.sh script must support path rollback, not just application rollback.

**Application rollback and this contract.** Because `/opt/hallptz` holds only code
and every customer-owned path sits outside it, an application rollback is a pure
re-deploy: `rollback.sh` checks the source checkout out at
`HALLPTZ_PREVIOUS_REF` (from `/etc/hallptz/install-state.env`) and re-runs
`install.sh`, which mirrors the tree with `rsync --delete`. Nothing under
`/etc/hallptz`, `/var/lib/hallptz`, `/var/log/hallptz` or `/var/backups/hallptz` is touched,
so `.provisioned` and both password secrets survive — the setup wizard does not
re-run after a rollback. Path rollback (moving data back to a legacy layout) is
the separate, still-outstanding concern described above.

---

## Backup/restore expectations

```text
Backup must include files from ALL canonical locations:
  /etc/hallptz/          site config
  /var/lib/hallptz/      runtime data
  Optional: /var/backups/hallptz/ manifest

Backup must record which path layout version was in use.

Restore must validate that target paths exist and are writable before writing.

Restore must use atomic write (.tmp → os.replace) for each file.

Restore must create .bak copies of existing files before overwriting.

Restore must not write outside the expected canonical paths.

Restore from a legacy-path backup into a canonical-path install:
  The installer/restore script must handle the location mismatch explicitly.
  It must not silently restore to the wrong location.

hallptz doctor must report which paths are in use and whether backup is current.
```

---

## Support bundle expectations

```text
Support bundle must read from canonical paths.
Support bundle must never include:
  /etc/shadow or any system password file
  SSH private keys
  Customer passwords or API tokens
  Raw ATEM IP or credentials unless redacted

hallptz doctor paths report must list all canonical and legacy paths and their state.
```

---

## Follow-up implementation issues identified

This contract document blocks:

```text
#499  Move runtime data from source tree to /var/lib/hallptz
#531  Define backup/restore manifest, dry-run and allowed-path contract
#532  Define sanitized support bundle export and redaction contract
```

Recommended follow-up issues to create after this contract is accepted:

```text
Implement /etc/hallptz/ and /var/lib/hallptz/ directory creation in installer
Update systemd unit to run as hallptz service user
Update data_paths.py to prefer canonical paths when running as service
Add hallptz doctor check for path layout and ownership
Add path layout version to backup manifest
Update rollback.sh to support path rollback
```

---

## Rule

No implementation issue may deviate from the path layout above without first
updating this document and getting a review comment acknowledging the change.

If hallptz doctor does not report the correct path layout, the installation is
not customer-ready.
