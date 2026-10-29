# Backup/Restore Manifest, Dry-Run and Allowed-Path Contract

Issue: #531.
Parent: #233.
Depends on: [Runtime Path Contract](RUNTIME_PATH_CONTRACT.md) (#530).

This document is the canonical contract for backup ZIP structure, restore
behaviour and safety rules. It must be reviewed before extending customer
restore behaviour or adding new data categories to backups.

---

## Backup ZIP structure

```text
backup-<ISO8601>.zip
├── manifest.json          Required. Must be validated before restoring any file.
├── <filename>.json        Customer data files (category: data).
└── config/
    └── <filename>.txt     Site config files (category: config).
```

Files must not use path traversal (no `../`, no absolute paths).
The root of the ZIP is the restore root. Subdirectories are allowed only
where the manifest explicitly defines them.

---

## Manifest schema

```json
{
  "manifest_version": 1,
  "created_at": "<ISO8601>",
  "app_version": "<semver>",
  "git_commit_or_build": "<hash or build tag>",
  "installation_id": "<uuid or unknown>",
  "profile": "<production|demo|support|unknown>",
  "backup_type": "<full|layout_only|support>",
  "source_paths": {
    "data": "<canonical path used at backup time>",
    "config": "<canonical path used at backup time>"
  },
  "files": [
    {
      "path": "<archive path>",
      "sha256": "<hex>",
      "size": 1234,
      "category": "<data|config|log|meta>",
      "restore_policy": "<required|optional|skip>"
    }
  ],
  "excluded_categories": ["<category>"],
  "restore_capable": true
}
```

### Required manifest fields

```text
manifest_version      integer, must be 1 for this contract version
created_at            ISO 8601 timestamp
app_version           semver string
backup_type           "full", "layout_only" or "support"
restore_capable       boolean — false means the ZIP must not be used for restore
files                 array, at least one entry required for a non-empty backup
```

### Optional but recommended

```text
git_commit_or_build   traceability to the code that created the backup
installation_id       site identity for support correlation
profile               runtime profile in use at backup time
source_paths          which canonical paths were backed up
excluded_categories   explicit list of what was not included
```

---

## Backup types

### full

Includes all restorable customer data and site config:

```text
config.yaml
chairman_presets.json
seat_names.json
schedule.json
room_layout.json
change_history.json
preset_brightness.json
atem_mapping.json
```

`restore_capable: true`.

This list is not maintained here. `domain/backup_contract.py` is the single
definition, and both `BackupService` and `RestoreService` derive their file set
from it — the table above documents what that module currently says.

That indirection exists because the two sides drifted once: `preset_brightness.json`
was added to the backup side only, and because `RestoreService` treats an
unlisted archive member as tampering, it rejected the **whole** archive —
`config.yaml` and presets included. Every appliance where an operator had
adjusted preset brightness could no longer be restored from its own backup, and
the failure surfaced only during a recovery.

`atem_mapping.json` joined the set when it moved out of `/etc/hallptz` (which the
service cannot write) into the runtime data directory. A backup taken before
that move does not contain it; restoring one simply leaves the current mapping
in place.

### layout_only

Includes only room layout and seat names — safe to restore without touching
session state, presets or network config:

```text
room_layout.json
seat_names.json
```

`restore_capable: true`.
Must not overwrite `chairman_presets.json` or network config unless explicitly
requested and the manifest explicitly includes them.

### support

A diagnostic snapshot for remote support — not intended for restore.

```text
hallptz doctor output
sanitized config summary
recent log excerpt (redacted)
systemd status summary
installation/profile/connectivity summary
backup metadata summary (not backup contents)
```

`restore_capable: false`.
If a restore attempt is made with a support bundle, the restore must fail
with a clear error referencing this contract.

---

## Allowed restore paths

Restore must write only to paths registered in the runtime path contract.

| Category | Allowed restore destination |
|---|---|
| `data` | `/var/lib/hallptz/` (canonical) or `~/.config/hallptz/` (legacy) |
| `config` | `/etc/hallptz/` (canonical) or app directory (legacy) |
| `log` | Not restorable — logs are diagnostic only |
| `meta` | Not written to disk — used for validation only |

Rules:

```text
Never write to paths outside the allowed destinations.
Never follow symlinks from the archive.
Reject any archive entry whose resolved path is outside the allowed destination.
Path traversal attempts (../, absolute paths) must abort the entire restore.
```

---

## Dry-run behaviour

When `--dry-run` is passed to the restore command:

```text
1. Validate manifest (schema, version, restore_capable).
2. Verify each file's sha256 against the archive.
3. Resolve each target path.
4. Check whether target exists, would be overwritten, or would be created.
5. Check whether a pre-restore backup can be created.
6. Report a table of actions — no file is written.
```

Dry-run output format (one row per file):

```text
<archive path>  ->  <target path>  [action: create|overwrite|skip]  [pre-backup: yes|no|n/a]
```

Dry-run must exit 0 if no errors are found, non-zero otherwise.

---

## Pre-restore backup

Before restoring any file that already exists at the target path:

```text
1. Create a timestamped pre-restore backup ZIP in /var/backups/hallptz/
   (or ~/.config/hallptz/ for legacy installs).
   Name: pre-restore-<ISO8601>.zip
2. Include all files that will be overwritten.
3. If the pre-restore backup cannot be written, abort the restore unless
   the operator explicitly passes --skip-pre-backup (must be logged as a warning).
4. Log the pre-restore backup path to the restore report.
```

---

## Atomic write behaviour

Each file restored to disk must use atomic write:

```text
1. Write content to <target>.tmp
2. Verify sha256 of <target>.tmp matches manifest
3. os.replace(<target>.tmp, <target>)
```

If any step fails:

```text
Remove <target>.tmp
Log the failure
Continue restoring remaining files (partial restore is acceptable)
Report which files failed at the end
Exit with non-zero status if any file failed
```

---

## Corrupt, unknown and unsafe archive handling

| Condition | Required behaviour |
|---|---|
| ZIP is corrupt or unreadable | Abort immediately, do not write any file |
| manifest.json missing | Abort immediately |
| manifest_version unknown | Abort immediately |
| restore_capable: false | Abort with clear error (support bundles are not restore backups) |
| File in archive not listed in manifest | Skip, log a warning |
| sha256 mismatch | Skip the affected file, log an error, continue with remaining files |
| Path traversal in archive entry | Abort immediately, do not write any file |
| Target path outside allowed destinations | Abort immediately, do not write any file |
| JSON file does not parse | Skip the affected file, log an error |
| JSON file is not a dict | Skip the affected file, log an error |

---

## Restore report

After restore completes, print a report:

```text
Restore report
  Source:       <zip path>
  Backup type:  <full|layout_only|support>
  Created at:   <ISO8601>
  App version:  <semver>

  Pre-restore backup: <path> [or: skipped / not required]

  Files restored:
    <target path>        OK
    ...

  Files skipped or failed:
    <archive path>       <reason>
    ...

  Status: SUCCESS | PARTIAL | FAILED
```

Exit code:
- 0 — all files restored successfully
- 1 — one or more files failed or were skipped
- 2 — restore aborted (corrupt/invalid/unsafe archive)

---

## Session safety

Do not restore while a live event session is active (`session.active` exists):

```text
If session.active exists:
  Abort restore.
  Print: "Cannot restore during an active session. End the session first."
  Exit 2.
```

---

## Layout-only restore boundary

Layout-only restore (`backup_type: layout_only`) must:

```text
Restore room_layout.json and seat_names.json only.
Not overwrite chairman_presets.json unless the manifest explicitly lists it.
Not overwrite network config (PTZ1IP.txt etc.) unless explicitly listed.
Not overwrite schedule.json unless explicitly listed.
```

If a full backup is passed where a layout-only restore was requested:

```text
Restore only the layout_only category files.
Log which files were skipped.
```

---

## Follow-up implementation issues

This contract blocks or informs:

```text
#532  Support bundle export and redaction contract
Update data_paths.py: add manifest generation to export_backup()
Update data_paths.py: add manifest validation to import_backup()
Add dry-run flag to hallptz restore command
Add pre-restore backup step to hallptz restore command
Add session.active check to hallptz restore command
Add sha256 verification to import_backup()
Add path traversal guard to import_backup()
Add restore report to hallptz restore command output
```

---

## Rule

No restore implementation may add new restorable file categories without
updating this contract and the runtime path contract (#530).

If a restore does not produce a restore report, it is incomplete.
