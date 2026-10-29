# Black Box Event Schema, Retention and Redaction Policy

> Issue: #487  
> Status: Adopted — MVP  
> Last updated: 2026-05-12

---

## Purpose

The Hall PTZ Control flight recorder writes structured local events so that support
can reconstruct what happened before a failure without requiring remote access or
live reproduction.

This document defines:

- The JSON event schema.
- The initial event type list.
- Redaction rules (what must never appear in the log).
- Retention and rotation policy.
- Storage ownership decision.
- Support bundle inclusion policy.

---

## Event schema

Each event is one JSON object per line (JSONL), UTF-8, append-only.

```json
{
  "schema_version": 1,
  "timestamp": "2026-05-08T15:42:12.231Z",
  "level": "INFO",
  "event_type": "SeatPresetRecallRequested",
  "app_version": "3.22.0",
  "git_commit": null,
  "installation_id": "hallptz-2026-0007",
  "installation_profile": "starter_1_camera",
  "runtime_mode": "production",
  "session_id": "session-20260508-1",
  "correlation_id": "cmd-20260508-001",
  "source": "operator_ui",
  "result": "requested",
  "message": "",
  "seat_id": "seat-2",
  "seat_label": null,
  "camera_role": "main",
  "camera_id": "cam-1",
  "preset": "preset-2",
  "error_code": null,
  "duration_ms": null,
  "extra": {}
}
```

### Required fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | int | Always `1` for this revision |
| `timestamp` | string | ISO-8601 UTC |
| `level` | string | `INFO` / `WARNING` / `ERROR` |
| `event_type` | string | See event type list below |
| `app_version` | string | Semver string from VERSION file |
| `installation_profile` | string | Config profile name |
| `runtime_mode` | string | `production` / `demo` / `simulation` |
| `session_id` | string | Active session id, or `"none"` |
| `correlation_id` | string | Command / request trace id |
| `source` | string | Origin: `operator_ui` / `setup` / `cli` / `atem` / `support` / `system` |
| `result` | string | `requested` / `sent` / `succeeded` / `failed` / `skipped` / `unknown` |

### Optional fields

| Field | Type | Description |
|---|---|---|
| `installation_id` | string | Assigned site id, default `"unknown"` |
| `git_commit` | string or null | Short commit hash if available |
| `message` | string | Human-readable detail, no secrets |
| `seat_id` | string or null | Stable seat identifier |
| `seat_label` | string or null | Display label (avoid personal names) |
| `camera_role` | string or null | e.g. `"main"`, `"wide"` |
| `camera_id` | string or null | Camera config key |
| `preset` | string or null | Preset identifier |
| `error_code` | string or null | Stable error code string |
| `duration_ms` | int or null | Round-trip or processing time |
| `extra` | object | Additional context; must pass redaction |

---

## Event type list

### MVP event types

| Event type | Level | Description |
|---|---|---|
| `AppStarted` | INFO | Application process launched |
| `AppStopped` | INFO | Application exited cleanly |
| `AppCrashDetected` | ERROR | Unhandled exception caught by crash reporter |
| `VersionLoaded` | INFO | VERSION file read at startup |
| `ConfigLoaded` | INFO | config.yaml loaded successfully |
| `ConfigValidationFailed` | ERROR | config.yaml failed schema validation |
| `SessionStarted` | INFO | Operator session started |
| `SessionEnded` | INFO | Operator session ended |
| `SeatPresetRecallRequested` | INFO | Operator pressed a preset button |
| `CameraCommandSent` | INFO | VISCA command dispatched to camera |
| `CameraCommandSucceeded` | INFO | Camera confirmed command |
| `CameraCommandFailed` | ERROR | Camera returned error or timed out |
| `SpecialPresetRecallRequested` | INFO | Home / lock / emergency preset triggered |
| `EmergencyStopPressed` | WARNING | Emergency stop invoked |
| `DoctorRun` | INFO | Diagnostics run completed |
| `BackupCreated` | INFO | Backup archive written |
| `RestoreStarted` | INFO | Restore operation started |
| `RestoreFailed` | ERROR | Restore operation failed |
| `SupportBundleExported` | INFO | Support bundle created and exported |

### Later event types (not MVP)

```text
SetupStarted / SetupCompleted / SetupBlocked
PreflightFailed
LicenseInvalid
AdminLoginSucceeded / AdminLoginFailed
PresetOverwriteConfirmed
LayoutChanged
CalibrationSaved
BaselineMismatchDetected
```

---

## Redaction rules

The following must never appear in any event field:

```text
passwords
password.enc contents
SSH credentials or private keys
licence private signing keys
tokens or API keys
raw secrets of any kind
unnecessary personal data (attendee names, contact details)
```

The recorder applies `redact_event_dict()` from `domain/blackbox_event.py` before
writing each event.  Callers are responsible for not passing secrets as field values.

### Preferred identifiers

Use stable technical identifiers instead of personal names:

```text
seat_id, seat_label (stable display label, not a personal name)
camera_role, camera_id
preset
profile, runtime_mode
result, error_code
```

---

## Retention and rotation policy

| Parameter | Value |
|---|---|
| Active file | `events.jsonl` |
| Max active file size | 10 MB |
| Rotated files | `events.1.jsonl` … `events.5.jsonl` |
| Total maximum storage | ~60 MB |
| Rotation trigger | File size check before each append |
| Rotation strategy | Rename-shift; oldest file deleted |

---

## Support bundle inclusion policy

The support bundle (`SupportBundleExported` event) includes:

- The last 500 events from `events.jsonl`, or the last 24 hours, whichever is smaller.
- Redaction is applied at write time; no re-redaction is needed at export.

---

## Storage ownership

Black box files live under the log directory:

```text
/var/log/hallptz/blackbox/events.jsonl
/var/log/hallptz/blackbox/events.1.jsonl
...
/var/log/hallptz/blackbox/events.5.jsonl
```

Rationale: `/var/log/` is conventional for operational logs on Linux.
`/var/lib/hallptz/` is reserved for persistent customer data (config, known-good
state, room layout).  The black box is operational telemetry, not customer data,
so `/var/log/hallptz/blackbox/` is the correct owner.

This aligns with `runtime/path_resolver.py` (`blackbox_dir`, `blackbox_events_file`).

---

## Privacy

MVP event data is scoped to stable technical identifiers.  Attendee or customer
personal names are not recorded by default.  Full privacy policy: `docs/PRIVACY_NOTES.md`.
