# Sanitized Support Bundle Export and Redaction Contract

Issue: #532.
Parent: #232.
Depends on: [Runtime Path Contract](RUNTIME_PATH_CONTRACT.md) (#530),
            [Backup/Restore Contract](BACKUP_RESTORE_CONTRACT.md) (#531).

This document defines what a KH PTZ Control support bundle may collect, what
must be redacted, and why a support bundle is not a restore backup.

---

## Purpose

A support bundle is a diagnostic snapshot exported by `khptz support-bundle` (or
equivalent). Its purpose is to give support personnel enough information to
diagnose a customer installation remotely — not to restore or copy the installation.

---

## Support bundle ZIP structure

```text
support-<ISO8601>-<installation_id_prefix>.zip
├── manifest.json          Required. restore_capable: false.
├── version.txt            khptz version output.
├── doctor.txt             khptz doctor output (structured, sanitized).
├── config_summary.json    Sanitized config summary (no secrets).
├── install_summary.json   Installation/profile/connectivity summary.
├── logs/
│   └── khptz.log.redacted  Recent app logs after redaction (windowed).
├── errors_summary.txt     Recent critical errors summary.
├── systemd_status.txt     systemd status summary (where available).
├── platform_summary.json  Raspberry Pi OS/runtime summary.
├── network_summary.json   Network readiness summary (no private secrets).
└── backup_meta.json       Backup metadata summary, not backup contents.
```

### Manifest fields for support bundles

All fields from the backup/restore manifest schema apply, plus:

```text
"restore_capable": false      Always false for support bundles.
"bundle_purpose": "support"   Distinguishes from restore backups.
"redaction_applied": true     Must be true if any redaction ran.
"redaction_version": 1        Version of the RedactionGuard rules applied.
```

If `restore_capable` is missing or is `true` in a support bundle, the export
is non-conforming and must not be distributed to support channels.

---

## Allowed information categories

The following may be included in a support bundle by default:

```text
khptz version and build identity
khptz doctor output (sanitized — no raw config values)
sanitized config summary (keys present/absent, not values for secrets)
installation ID and profile
connectivity summary (reachable/unreachable, not raw IPs unless safe)
recent app logs after redaction (windowed — see Log windowing below)
recent critical error summary (last N errors only)
systemd service status summary
Raspberry Pi OS version, Python version, disk space, RAM summary
backup metadata (created_at, backup_type, file count) — not backup contents
network readiness summary without private secrets
```

---

## Forbidden information categories

The following must never appear in a support bundle:

```text
Password fields (/etc/shadow, khptz passwords, customer passwords)
Private keys (SSH keys, licence signing keys, TLS private keys)
API tokens or bearer tokens
Licence private keys or signing material
Raw customer backup ZIPs or their contents
Raw support credentials
Unredacted config files (raw YAML/JSON with secret values)
Unbounded full log files
Personal data beyond installation/operator identifiers where not required
Private network topology details (unless explicitly approved per site)
```

---

## Redaction rules (RedactionGuard)

All collected files must pass through the RedactionGuard before inclusion.

### Always redact

```text
password, passwd, pwd, secret, token, api_key, auth, credential,
private_key, signing_key, licence_key, license_key
(case-insensitive key match in JSON/YAML)
```

Redacted value replacement: `"<REDACTED>"`.

### Redact by pattern

```text
IP addresses: include only if they are needed for connectivity diagnosis.
  If in doubt, replace with "<IP_REDACTED>".
Hostnames: include only public/local hostnames needed for diagnosis.
SSH keys: replace full key block with "<SSH_KEY_REDACTED>".
Tokens (bearer, JWT, API): replace with "<TOKEN_REDACTED>".
Paths containing /home/<user>/: replace user component with "<USER>".
```

### Fail closed

```text
If the RedactionGuard encounters a format it cannot parse safely, it must:
  - Exclude the file entirely.
  - Log a warning in the bundle manifest under "redaction_warnings".
  - Not include a partially redacted version.
```

### Redaction is not a legal guarantee

The support bundle export does not make legal or GDPR compliance guarantees.
For high-sensitivity installations, the operator should review the bundle
before sending it to any third party.

---

## Log windowing

Support bundle logs must be windowed, not full dumps:

```text
Default window:  last 500 lines of the most recent log file.
Maximum window:  last 2000 lines (explicit --verbose flag only).
Older rotated logs: excluded by default.
All included log lines must pass through the RedactionGuard.
```

Log file name in ZIP: `logs/khptz.log.redacted` (never `khptz.log`).

---

## Config summary rules

The config summary is a structural summary — not a raw config dump:

```text
Include: which config keys are present or absent.
Include: which cameras and profiles are configured (role names, not IPs).
Include: which optional features are enabled (ATEM: yes/no, schedule: yes/no).
Exclude: raw IP addresses unless needed for connectivity diagnosis.
Exclude: all secret-category values.
Exclude: raw YAML/JSON files.
```

The config summary must be generated programmatically, not by copying config files.

---

## Network summary rules

```text
Include: reachable/unreachable result per configured camera and ATEM.
Include: subnet summary (e.g. "cameras on 192.168.30.x").
Include: whether the Raspberry Pi has a static IP or DHCP.
Exclude: raw private keys, tokens, passwords.
Exclude: full routing tables or ARP tables unless explicitly requested.
```

If full IP addresses are included, they must be clearly marked as
potentially sensitive in the bundle README or manifest.

---

## How support bundles differ from backup ZIPs

| Property | Backup ZIP | Support bundle |
|---|---|---|
| Purpose | Customer data restore | Remote diagnosis |
| `restore_capable` | `true` | `false` |
| Contains raw data files | Yes | No |
| Contains redacted logs | No | Yes |
| Contains doctor output | No | Yes |
| Contains config summary | No | Yes (sanitized) |
| Can be used to restore | Yes | Never |
| Sent to support channels | Rarely / with permission | Yes (if consented) |

---

## Size and retention limits

```text
Maximum bundle ZIP size: 10 MB (hard limit — abort if exceeded).
Soft warning: log a warning if bundle exceeds 2 MB.
Bundle retention on device: 5 most recent bundles; older ones are deleted automatically.
Bundles older than 90 days should be deleted unless the operator opts out.
```

---

## Export-only, read-only

```text
Support bundle export must be read-only.
It must not change any runtime state.
It must not write to any path outside the support bundle output directory.
It must not start or stop any service.
It must not send data anywhere automatically — the operator must transmit it.
```

---

## Customer consent and transmission policy

```text
The support bundle must not be transmitted to any third party without explicit
operator consent recorded in the session.

The operator should be shown what the bundle contains before transmission.

Remote support tools must not export and transmit support bundles automatically
without operator confirmation.
```

---

## Acceptance criteria covered

- [x] Support bundle contract documented
- [x] Bundle manifest and categories defined
- [x] Forbidden information categories listed
- [x] Redaction rules defined (RedactionGuard specification)
- [x] Size and retention limits specified
- [x] Log windowing specified
- [x] Config summary rules specified
- [x] Network summary rules specified
- [x] How support bundles differ from backup ZIPs made explicit
- [x] Export-only/read-only rule stated
- [x] Consent and transmission policy stated

---

## Follow-up implementation issues

```text
Add RedactionGuard class to domain/supportability.py or application/
Implement khptz support-bundle command in runtime/cli.py
Implement config_summary generator (no raw values)
Implement network_summary from doctor check results
Implement log windowing with redaction pass
Add bundle size limit check
Add bundle retention cleanup
Add bundle manifest generation with redaction_applied field
Add test for RedactionGuard (known-secret patterns, fail-closed)
```

---

## Rule

If `redaction_applied` is not `true` in the manifest, the bundle must not be
sent to any external support channel.

If a support bundle restores data, it is a contract violation — report and audit.
