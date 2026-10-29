# Startup Gate UX Direction

This document records the post-MVP direction for the startup splash/status experience.

The concept is named `Startup Gate` because it is a safety and readiness gate before normal operation, not only a visual splash screen.

This is documentation/design only. It does not implement UI behaviour.

---

## Main states

Startup Gate should use only three main states:

```text
Ready
Warning
Blocked
```

### Ready

Use when the system can start normal operation.

Default operator path:

```text
System ready
Profile: Standard
Mode: Operator
Cameras: OK
Last backup: OK

[Start HALLPTZ]
```

Rules:

- Do not show `Run doctor` by default if everything is healthy.
- Do not overload the operator with support/admin buttons.
- Installer/admin/support users can access details through an explicit details/admin path.

### Warning

Use when operation can continue, but there are non-blocking risks.

Example:

```text
Ready with warnings
Camera 2 unavailable
Last backup old

[Start with warnings]
[Run doctor]
[Find missing camera]
[Export support bundle]
[Exit]
```

Rules:

- `Start with warnings` must be deliberate.
- Warnings must explain what is affected.
- Hardware checks must use bounded timeouts and must not freeze the screen.

### Blocked

Use when normal operation should not start.

Example:

```text
Startup blocked
Invalid config.yaml

[Show error]
[Run doctor]
[Restore last known good config]
[Export support bundle]
[Exit]
```

Rules:

- Invalid config blocks normal operation.
- Invalid layout blocks normal operation where the product cannot safely render/control seats.
- Required camera missing can block startup/session start depending on profile policy.
- The user must be given a recovery path, not only an error.

---

## Config failure behaviour

When `config.yaml` fails validation, Startup Gate should provide:

- clear error summary;
- line, field or path where available;
- expected value or allowed options where available;
- `Run doctor` if useful;
- `Restore last known good config` where backup/history exists;
- diagnostics-only safe mode where practical;
- `Exit`.

Do not allow normal operation with invalid config unless a later documented policy explicitly permits a safe degraded mode.

---

## Required camera missing behaviour

When a required camera is missing, show a targeted helper:

```text
Required camera missing: comments
Expected IP: 192.168.1.22
Suggested checks:
- camera power
- Ethernet cable
- camera IP
- VISCA port
- same subnet as Raspberry Pi
```

Provide `Find missing camera` where practical.

Startup Gate should consume diagnostics/readiness services instead of duplicating network or camera probing logic.

---

## Support bundle behaviour

If #27 support bundle export is available, Startup Gate may expose:

```text
[Export support bundle]
```

Rules:

- Do not implement support bundle logic inside Startup Gate.
- Call the support/export service.
- If unavailable, show `Support bundle unavailable` only in details/admin/support context.
- Support bundle output must use the current redaction rules.

---

## Demo mode behaviour

Demo mode must be impossible to confuse with production.

Minimum display:

```text
DEMO MODE - NO REAL HARDWARE COMMANDS
```

Rules:

- Demo should use a distinct visual treatment/banner.
- Demo start button should say `Start Demo`, not only `Start HALLPTZ`.
- Demo validation must not be presented as pilot/customer readiness.

---

## Pilot readiness display

Only installer/admin/support context should show pilot readiness.

Allowed states:

```text
Pilot readiness: ready
Pilot readiness: ready with limitations
Pilot readiness: not ready
```

Examples:

```text
Pilot readiness: NOT READY
Reason: real Raspberry Pi validation missing
```

```text
Pilot readiness: READY WITH LIMITATIONS
Limitations: ATEM not tested
```

Rules:

- This should reflect #381/#520 evidence.
- Do not duplicate #381 validation logic inside the UI.
- Operator mode should not be cluttered with pilot-readiness details.

---

## Last known good summary

Where data exists, show:

```text
Last successful startup: 2026-05-08 18:42
Last backup: 2026-05-08 18:30
Last config change: 2026-05-09 10:12
```

Rules:

- Missing data should be shown honestly as unavailable or unknown.
- Do not block startup only because last-known-good metadata is unavailable.
- Do not expose unnecessary personal/customer data.

---

## Ownership boundaries

Startup Gate owns:

- visible startup/readiness state presentation;
- Start / Start with warnings / blocked recovery entry points;
- simple/details split;
- calling existing diagnostics/support services;
- demo banner/start wording;
- admin/installer pilot-readiness summary display.

Startup Gate must not own:

- low-level diagnostics implementation;
- camera probing logic;
- support bundle generation;
- backup/restore implementation;
- licensing enforcement;
- setup wizard implementation;
- full admin access control;
- report schema ownership.

---

## Priority stance

Startup Gate is post-MVP / first-pilot polish.

It should not block the first MVP release by default. It can become a blocker later only if #381/#520 validation shows startup confusion, unsafe demo/startup behaviour or config recovery gaps preventing pilot/customer use.
