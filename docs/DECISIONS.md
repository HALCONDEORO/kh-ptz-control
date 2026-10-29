# Project Decisions

This document records important product and technical decisions for KH PTZ Control.

Use it to avoid re-opening the same debates and to keep AI-assisted development aligned with the project direction.

---

## Product direction

- The product is offline-first.
- The first production target is a Raspberry Pi touchscreen installation.
- The first commercial goal is an installable and supportable local system, not a cloud platform.
- Online licensing, dashboards and remote management are future options, not MVP requirements.
- Demo mode must be safe and must not touch production configuration.
- Demo mode must never send real commands to cameras or ATEM, and the UI/diagnostics must make demo/no-hardware state unmistakable.
- Customer installs should come from tagged releases or approved release-candidate branches, not random commits from `main`.
- A build that has only passed demo/no-hardware validation is not pilot-ready or customer-ready.

---

## Commercial package direction

Initial commercial package assumptions:

| Package | Direction |
|---|---|
| Starter | Official one-camera product profile. |
| Standard | Official two-camera product profile. |
| Pro / Enterprise / Custom | Future or explicitly scoped non-standard installation. |
| Demo | Fake/safe demo profile by default. |

Package limits should eventually be enforced by offline license and config/profile validation. Future tier decisions should preserve clear separation between Starter, Standard, Pro and Enterprise.

---

## Scope decisions

- Config and layout are separate.
  - Config = hardware, runtime, features, installation identity.
  - Layout = room, seats, labels, preset mapping.
- JSON remains the first storage target.
- SQLite is not required for the MVP unless a future issue proves a clear need.
- MVP should focus on installation, diagnostics, backup/restore and layout foundation.
- Visual layout editing, advanced ATEM, multi-room, cloud and online licensing are post-MVP/future.
- Supportability is a product requirement, not an optional extra.

---

## Architecture decisions

For formal ADR entries (context, decision, consequences) see [`docs/ARCHITECTURE_DECISIONS.md`](ARCHITECTURE_DECISIONS.md).

- `ApplicationController` is the public command API for UI-originated product actions.
- `AsyncEventBus` is for events, notifications, diagnostics, logging and integrations.
- Short rule: `ApplicationController` commands; `AsyncEventBus` informs.
- For the full command/event policy with workflow table, see [`docs/COMMAND_EVENT_POLICY.md`](COMMAND_EVENT_POLICY.md).
- Do not create another camera controller.
- `CameraManager` (`ptz/visca/manager.py`) owns VISCA workers/connections; it is internal to `ViscaCameraAdapter`.
- `CameraPort` (`ports/camera_port.py`) is the application-level camera interface.
- `ViscaCameraAdapter` (`adapters/visca_camera_adapter.py`) implements `CameraPort` and owns all socket/VISCA details.
- Architecture migration complete (3.38.x): `CameraService` and `ViscaController` have been removed.
- New business logic should move to application/domain services.
- Legacy Qt controllers should not receive new business logic unless explicitly accepted.
- Domain/application logic should not depend on PyQt.
- UI should request behaviour; it should not own camera protocol, persistence or business rules.
- Old direct UI-to-VISCA command paths should be removed or migrated behind the application/service boundary.
- Camera command handling should be designed for safety: no accidental movement, no silent failures, clear feedback and testable fake adapters.
- `JoystickAdapter` is the single active input adapter: wired in main_window via AsyncEventBus.
- `SeatAdapter` was removed (2026-05-25): seat input must go through ApplicationController to enforce CALL/SET policy. Direct bus emission from seat buttons bypasses policy.

---

## CALL/SET interaction decisions

- Left click / short tap means CALL wherever the current mode allows CALL.
- Right click / long press means SET only in admin or installer contexts.
- SET must require explicit confirmation before overwriting a real preset.
- MVP SET confirmation does not require a PIN unless a later access-control decision changes that.
- Normal operator flows must not accidentally expose SET.
- Session start should be blocked when a required camera is missing.
- Required-camera failures should identify the missing camera and provide diagnostic/remediation guidance where practical.

---

## Seat/layout decisions

- Seat identity, visible label, preset number and camera role should be separate concepts.
- A visual seat move must not automatically change preset identity.
- A visible label/name change must not automatically change preset identity.
- Camera routing should move toward explicit `camera_role`, not current selected camera assumptions.
- `room_layout.json` owns room/seats/layout/preset mapping data.
- Visual layout editor work waits until layout persistence and seat identity rules are safe.

---

## Site metadata decisions

The site metadata foundation is:

```yaml
site:
  installation_id: "khptz-2026-0007"
  customer_name: "Customer Name"
  room_name: "Main Hall"
  installation_profile: "standard_2_camera"

runtime:
  connectivity_mode: "offline"
```

Rules:

- `installation_id` must be stable after installation.
- Backups, support records and future license files should reference the same installation ID.
- Demo data should use demo identity, not a real customer identity.

Ownership:

| Field | Owner area |
|---|---|
| `site.installation_id` | site metadata / licensing / support |
| `site.installation_profile` | package/profile selection |
| `runtime.connectivity_mode` | offline-first runtime behaviour |
| change history / diff logic | support hardening |

---

## Diagnostics and support decisions

Readiness and diagnostics use common severity values:

```text
OK
WARNING
ERROR
NOT_APPLICABLE
```

Diagnostics should detect and report first.

Automatic repair should only be added later when it is safe, explicit and tested.

Support direction:

- `khptz doctor` is the first diagnostic command.
- `khptz doctor` is required before closing an installation and should be surfaced in installer/setup flows as an action the installer can run.
- `khptz backup` should be used before risky support work.
- Backup is mandatory before update or restore operations unless a documented emergency exception is accepted.
- Restore must validate before writing.
- Support bundle export should be available from both CLI and UI.
- Support bundle export should be sanitized and must not include secrets.
- Persistent logs are needed for serious paid support.
- Startup logs should include app version, git commit/build where available and active profile/mode.
- Future support direction includes a local black box / flight recorder for important operational events such as session start/end, preset recall, camera errors and backup creation.

---

## Deployment decisions

- GitHub Actions must not deploy automatically to customer Raspberry Pis.
- Heavy release checks should be manual, not run on every commit.
- Installer/systemd work must protect customer data.
- Production Raspberry Pi installs should use a dedicated `khptz` service/user account.
- Production application code, configuration, runtime data and logs should move toward `/opt/khptz`, `/etc/khptz`, `/var/lib/khptz` and `/var/log/khptz`.
- Customer/runtime data must not live in the repository/application folder in production installs.
- Restore must validate before writing and should create a pre-restore backup.
- Golden backups must not be deleted automatically.
- Rollback must be considered part of update safety, not an afterthought.
- Customer deployment should require release checklist review.

---

## Demo decisions

- Demo mode must be visibly separate from production.
- Demo mode should use fake camera/ATEM adapters by default.
- Demo mode must display wording equivalent to `DEMO MODE - NO REAL HARDWARE COMMANDS` wherever readiness/startup state could be confused with production.
- Demo reset should only reset demo/sample data.
- Legacy simulation helper may remain during transition, but must not be confused with production runtime.

---

## Startup Gate direction

The post-MVP startup/splash/status concept is named `Startup Gate` because it is a safety and readiness gate before normal operation.

Startup Gate should use three main states:

```text
Ready
Warning
Blocked
```

Rules:

- Invalid `config.yaml` blocks normal operation, but must offer repair or recovery guidance instead of leaving the user stuck.
- `Run doctor` appears only when useful or through details/admin/support context; it should not clutter a clean Ready path.
- `Find missing camera` appears when a required camera is missing.
- `Export support bundle` appears when the support bundle service is available.
- Demo mode must be impossible to confuse with production.
- Installer/admin contexts may show pilot readiness as `ready`, `ready with limitations` or `not ready`.
- Last-known-good startup, backup and config-change metadata should be shown where available, without blocking startup only because metadata is missing.
- Startup Gate consumes diagnostics/readiness/support services; it must not duplicate low-level probing, support bundle, backup/restore or licensing logic.
- Startup Gate is post-MVP / first-pilot polish and does not block the first MVP release unless #381/#520 evidence promotes it.

---

## Layout editing and admin decisions

- Editable room layout is future roadmap work.
- Layout editing is installer/admin-only.
- Customers/operators should not be able to move, create or delete seats outside an authorised admin/installer context.

---

## Licensing decisions

- Offline signed licensing is the first licensing direction.
- Private signing keys must never be committed to the repo.
- License checks should read installation identity and profile from site metadata.
- License should eventually enforce plan, expiry, camera count and feature flags for separable Starter, Standard, Pro and Enterprise features.
- Online validation is future, optional and not required for MVP.

---

## Current release target

```text
v0.1.0-installable-mvp
```

Current state:

```text
Installable MVP candidate. Release-candidate QA and Raspberry Pi hardware validation remain before customer deployment.
```

This target is defined in `docs/IMPLEMENTATION_PLAN.md` and issue #288.
