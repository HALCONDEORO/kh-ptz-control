# Known Limitations

This document lists current product and code limitations. Update it when the related work is completed or validated.

Current overall state:

```text
Working application + installable MVP candidate.
Not yet a fully validated customer release.
```

---

## Release readiness

- The repository contains CLI, installer, systemd, backup/restore, rollback and demo foundations.
- These assets still need real Raspberry Pi validation before being treated as customer-ready.
- Customer installs should use tagged releases/release candidates, not random commits from `main`.
- A real hardware soak test is still required before first paid deployment.

---

## Architecture

- The codebase is still hybrid: `ApplicationController` is the enforced UI boundary, but legacy PyQt controllers remain active.
- `CameraPort` (`ports/camera_port.py`) and `ViscaCameraAdapter` (`adapters/visca_camera_adapter.py`) are fully implemented and integrated; all primary camera commands route through this boundary. `CameraService` has been removed.
- The `TEMPORARY_IMPORT_EXCEPTION` that used to cover `ui/config_dialog.py` (#686) has been removed; the exception budget is now capped at 0 by the guard test.
- Architecture boundary tests pass with zero violations and zero declared exceptions.

---

## Configuration

- Camera IPs are now injected from `config.yaml` via `CameraRegistry`; legacy `.txt` files are deprecated but not fully retired — dual-loader risk exists until `.txt` files are removed (see `docs/STATE_OWNERSHIP_AUDIT.md`).
- Full customer/runtime data separation from application source code still needs further hardening.
- Config change history and config diff diagnostics are not complete.
- Offline license-related config fields are not fully enforced yet.

---

## Layout and seating

- Seat buttons now render from `LayoutService` / `room_layout.json` with `SEAT_POSITIONS` fallback; the hardcoded `SEAT_POSITIONS` dict in `config/__init__.py` is still present during migration.
- The full visual layout editor is not complete yet.
- Seat identity is not fully decoupled everywhere into `seat_id`, `label`, `preset` and `camera_role`.
- Seat identity labels live only in `room_layout.json` (`SeatLayout.label`). `seat_names.json` stores the people roster and the person→seat assignment, not seat labels — the two files are distinct concerns and do not duplicate seat labels. (An earlier note claiming duplicate seat-label storage was a terminology mix-up; see `docs/STATE_OWNERSHIP_AUDIT.md`.)
- Guided seat preset calibration is not complete.
- Multi-room profiles are not complete.

---

## ATEM integration

- ATEM support is optional and partial.
- Diagnostics/fake ATEM foundations exist, but full production ATEM service separation and advanced safety controls are not complete.
- Live ATEM automation should not be treated as a finished customer feature until safety modes, mapping and admin controls are validated.
- Missing ATEM should not break non-ATEM installations, but this should be tested per profile.

---

## Demo and simulation

- Demo ATEM control panel exists for manual fake-ATEM interaction; demo profile regression tests pass.
- `FakeCameraPort` implements the `CameraPort` protocol for hardware-free tests.
- Demo mode still needs full manual UI/customer-facing polish; guided sales scenario playback is not complete.
- Legacy `sim_mode.py` still exists and can touch legacy IP files, so it must be checked before production-style testing.
- Demo/prod isolation must be validated on Raspberry Pi before sales/customer demonstrations.

---

## VISCA and camera behaviour

- VISCA response validation has improved, but real camera models may still expose edge cases.
- Camera command queuing, cancellation, STOP priority and latency handling still need real-world validation.
- Rapid operator input, long-running sessions and network-loss recovery need soak testing.
- Blocking socket work should continue moving away from UI paths.

---

## Deployment and operations

- Installer, systemd service and rollback scripts exist, but need repeated Raspberry Pi QA.
- Persistent rotating production logging is implemented and wired into both `main.py` and the `khptz` CLI entry points (`runtime/logging_setup.py`); sanitized support bundle export is implemented (`application/support_bundle_service.py`, `khptz support-bundle`). Both still need real Raspberry Pi validation, not further implementation.
- `runtime/installer/rollback.sh` previously assumed the pre-#530 layout (data files inside the install directory); it has been updated to match the current `/opt/khptz` + `/etc/khptz` + `/var/lib/khptz` contract and now takes its safety snapshot via `khptz backup` instead of a hand-rolled file list.
- Rollback is a **re-deploy**, not an in-place `git checkout`: `/opt/khptz` is an rsync'd artifact with no `.git` and no write access for the service user. `install.sh` records the source checkout and the previous ref in `/etc/khptz/install-state.env`, and `rollback.sh` checks that checkout out at the previous ref and re-runs `install.sh`. Installs made before `install-state.env` existed must pass `--source` and `--to` explicitly. Untested on real hardware — part of the Pi validation gate (#381).
- The session-owned GUI (`--gui-mode user`, #885) ships complete — user unit, XDG autostart launcher, group-boundary data access, mutual exclusion with the system service and rollback preservation — but is **not the default and has never run on hardware**. `--gui-mode system` (the validated path, with the scoped `xhost` helper) remains the default until the merged fixes are accepted on the physical appliance (#890). Cutting over is one flag, and switching back is the same flag.
- **`--gui-mode user` is incompatible with local password verification (open decision).** Passwords are verified in-process: the login screen and role-elevation overlay call `verify_entry` / `verify_admin`, which decrypt `password.enc` / `admin.enc` directly. Under `--gui-mode user` the GUI runs as the desktop account, so either the secrets stay `0600 khptz:khptz` and **nobody can log in**, or they are made group-readable and the desktop account can decrypt the **administrator** password — the key is derived from `/etc/machine-id`, which is world-readable — defeating the operator/administrator split. The installer currently keeps secrets private (fails visibly rather than weakening the role model), which means `--gui-mode user` cannot authenticate yet. Resolving it properly means moving password verification behind the privileged provisioning channel, as Repair already does. This does not affect the default `--gui-mode system`, where the GUI runs as `khptz` and owns the secrets.
- Linux permissions for service user, config, logs, backups and password file still need review before customer deployment.
- Golden image/provisioning should be validated before multiple installs.

---

## Licensing and commercial controls

- Offline signed license validation is not implemented yet.
- Plan enforcement for Starter/Standard/Professional/Enterprise is not active.
- Camera count and feature limits are not yet enforced by license.
- Online license validation, cloud dashboard and billing integration are future work.

---

## Testing

- Unit, architecture, lint and workflow checks exist.
- Hardware-free tests do not replace manual Raspberry Pi validation.
- Real PTZ cameras, ATEM-enabled/disabled cases, touchscreen input, systemd boot, backup/restore and rollback must still be validated on target hardware.
- Day-run/soak testing should be performed before first customer deployment.

---

## Final rule

Treat the current codebase as:

```text
good enough for controlled QA and release-candidate preparation
not yet good enough for unattended customer deployment without validation
```

## Pre-release review follow-ups (2026-10-29)

### Crashing GUI stays down after three failures
`khptz-control.service` gives up after 3 failures in 60 s (StartLimitBurst).
The display-ready path resets the unit at the next login, but mid-meeting the
operator recovers it by hand:

    systemctl reset-failed khptz-control && systemctl start khptz-control

Rehearse this once before relying on it. Deliberate: an aggressive restart
loop can hide a crash loop behind a flickering display.

### Python 3.11 / 3.13 support level
The installer warns (does not refuse) on interpreters other than the tested
baseline. Python 3.13 removed stdlib modules and ships different PyQt5 builds.
Before running on an OS with a non-baseline Python, validate by hand:
`khptz doctor` and a full GUI session. The VISCA layer itself is 3.9-safe.

### Password files in `--gui-mode user`
The `*.enc` password files stay `0600` owned by the `khptz` service user. In
user GUI mode the GUI runs as the desktop user and may not be able to verify
logins. Until this path is reviewed, provisioned installs should stay on
`--gui-mode system` (the default).

### Provisioning privilege boundary (review notes)
Recorded for the pending security review, not a confirmed defect:
- `/run/khptz` is owned by the desktop user and a root oneshot consumes
  `request.json` from it; symlink/TOCTOU handling lives in `provision.py`.
- The desktop user joins the `khptz` group (can read `config.yaml` and
  `install-state.env`).
- The secret key is derived from the world-readable `/etc/machine-id`.

### Blocking semantics of confirmed camera commands (v7/v8 scope)
Confirmed commands (power, standby, focus, preset recall/save) block their
caller until the camera answers, bounded by fast-connect (3 immediate
attempts) + read timeout (~10 s worst case when the camera is down), and a
STOP interrupts them with immediate failure.
- Session power on/off runs on background threads (`SessionPowerOn` /
  `SessionStandby`) — the UI never freezes on session start/end.
- Power-on cancellation contract: a failed or STOP-interrupted `power_on`
  aborts the rest of the sequence (cam2 is never commanded blindly), and
  ending the session mid-startup cancels the remaining power-ons. Standby
  always completes both cameras (off is the safe operation).
- The config-page preset test runner is threaded already.
- Remaining synchronous callers on the UI thread, accepted scope for the
  field test: the right-panel focus buttons (single bounded command each,
  STOP-interruptible). Moving them off-thread requires reworking how their
  results update button state — tracked as post-test work.
