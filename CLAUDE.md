# Claude Code instructions

Use this file as the working contract for Claude Code in this repository.

## Product context

Hall PTZ Control is a Raspberry Pi touchscreen application for VISCA-over-IP PTZ camera control. It is moving from a working fixed-site application into a configurable commercial product.

**Current version:** 3.38.3

**Current state:**

```text
Installable MVP candidate (v0.1.0-installable-mvp target).
Core CLI, installer, systemd, diagnostics, backup/restore, demo foundations and
architecture boundary enforcement all exist and are tested.
Raspberry Pi hardware QA and support bundle MVP remain before first customer deployment.
```

The product must stay reliable for offline-first customer installations. It runs headless on a Pi as a systemd service controlled through a touchscreen.

---

## Working mode

- Work on one GitHub issue or focused task at a time.
- Use a focused branch named for the issue.
- Keep the diff small.
- Prefer readable, boring code over clever code.
- Do not silently change behaviour outside the issue scope.
- Do not merge your own PR unless explicitly instructed by the human owner.
- Do not install/deploy customer systems from random commits; use tags or approved release-candidate branches.
- Customer installs require Pi validation (#381) and support bundle MVP (#27) before pilot readiness.

---

## Hard rules

- Never commit secrets, private keys, customer passwords, real customer config or private network details.
- Never add automatic customer deployment.
- Never add licensing/payment/legal/pricing changes without explicit human review.
- Never add new business logic to legacy Qt controllers when a service layer is appropriate.
- Never create duplicate camera-control abstractions.
- Never bypass backup, restore or rollback safety for customer data.
- Never add new `ui/ → VISCA/socket` paths; all camera intent flows through `ApplicationController → CameraPort`.

---

## Where code should go

| Directory | Purpose |
|---|---|
| `domain/` | Pure rules, models and constants — no PyQt, no I/O, no sockets |
| `application/` | Product use cases and application services — no PyQt |
| `ports/` | Interfaces/boundaries (e.g. `CameraPort`) |
| `adapters/` | Hardware, storage and simulation implementations |
| `ptz/visca/` | VISCA protocol commands, parser, worker and transport |
| `ui/` | PyQt widgets, windows and UI wiring |
| `runtime/` | CLI (`hallptz`), installer helpers, systemd and diagnostics entry points |
| `core/` | Event bus (`AsyncEventBus`), `SystemState`, `Controller`, `Supervisor`, `AppContext` |
| `config/` | Config loading, schema, registry and writer |
| `tests/` | All automated tests (mirrors source layout) |
| `docs/` | Product, architecture and operations notes |
| `scripts/` | Build, release and tooling scripts |
| `bootstrap.py` | Single composition root — all service/adapter wiring |

`bootstrap.py` is the **only** place that may instantiate `SystemState`, `AsyncEventBus`, `PresetService`, `ViscaCameraAdapter`, `SessionService` or `Controller`.

---

## Architecture rules (ADRs)

Formal ADRs live in `docs/ARCHITECTURE_DECISIONS.md`. Short form:

**ADR-001 — UI never calls VISCA/hardware directly.**
All camera intent flows: `UI → ApplicationController → service → CameraPort → adapter → ptz/visca`.

**ADR-002 — `ApplicationController` is the single UI/application command boundary.**
UI widgets call only `ApplicationController` methods; they do not call services, ports or adapters directly.

**ADR-003 — `SessionService` owns the session lifecycle.**
Start, end and home go through `application/session_service.py`. No other layer initiates or terminates a session.

**ADR-004 — `CameraPort` is the hardware boundary for cameras.**
`ports/camera_port.py` separates application intent from VISCA/socket implementation.
Adapters: `ViscaCameraAdapter` (production), `FakeCameraPort` (demo/test).

**ADR-005 — `AsyncEventBus` reports events; commands are explicit calls.**
`ApplicationController` = commands (change state).
`AsyncEventBus` = events, notifications, diagnostics, logging and integrations.
The bus never carries primary commands.

**ADR-006 — Customer data writes go through services, never widgets.**
All writes to config, layout, presets or session state must go through an application service.

**ADR-007 — `CommandResult` is the hardware-level result shape.**
All `CameraPort` methods return `CommandResult`. Application services use `OperationResult` (domain/supportability.py).

---

## Allowed dependency direction

```
ui          → application
application → domain
application → ports
adapters    → ports, external libs/hardware
runtime     → application
bootstrap   → all (composition only)
```

**Forbidden imports (never add):**

```
domain      → PyQt5, socket, filesystem reads/writes
application → PyQt5
ui          → ptz.visca.commands (except documented TEMPORARY_IMPORT_EXCEPTIONS)
ui          → direct JSON persistence
adapters    → ui
```

Architecture boundary tests enforce these rules automatically — see `tests/test_architecture_boundaries.py`. The exception budget is capped at 0; the former `ui/config_dialog.py` exception (#686) was removed and the issue closed.

---

## Runtime paths (Raspberry Pi install)

```text
/opt/hallptz/           Application code (read-only in service use)
/etc/hallptz/           Customer/site config (config.yaml, room_layout.json)
/var/lib/hallptz/       Persistent runtime data (presets, session state, change history)
/var/log/hallptz/       Production logs and blackbox events
/var/backups/hallptz/   Local backup ZIPs
~/.config/hallptz/ Legacy data location — read-migrate source only
```

**Environment overrides** (tests/demo):

```bash
HALLPTZ_CONFIG_DIR        # overrides /etc/hallptz/
HALLPTZ_DATA_DIR          # overrides /var/lib/hallptz/
HALLPTZ_DATA_DIR     # legacy alias for HALLPTZ_DATA_DIR
HALLPTZ_LOG_DIR           # overrides /var/log/hallptz/
HALLPTZ_BACKUP_DIR        # overrides /var/backups/hallptz/
HALLPTZ_PROFILE           # runtime profile: production | demo | simulation
```

Tests run with `HALLPTZ_DATA_DIR` pointing to `.pytest-runtime/data/` (set in `conftest.py`) and `QT_QPA_PLATFORM=offscreen`. Never override these in code; they are set once in conftest.

---

## Startup order

`RuntimePathResolver` → `load_config` → validate config/layout → `build_app_context` (bootstrap) → `AsyncEventBus.start` → build ports/adapters → startup diagnostics → build UI from `AppContext` → decide Ready/Warning/Blocked → wait for operator action.

Session MUST NOT start automatically on boot. See `docs/LIFECYCLE_CONTRACT.md`.

---

## Key service map

| Service/class | Location | Role |
|---|---|---|
| `ApplicationController` | `application/app_controller.py` | Single UI command boundary |
| `SessionService` | `application/session_service.py` | Session start/end/home lifecycle |
| `CameraPort` | `ports/camera_port.py` | Hardware boundary protocol |
| `ViscaCameraAdapter` | `adapters/visca_camera_adapter.py` | Production CameraPort impl |
| `FakeCameraPort` | `adapters/fake_camera_port.py` | Test/demo CameraPort impl |
| `AsyncEventBus` | `core/events.py` | Notification/integration bus |
| `SystemState` | `core/state.py` | In-memory runtime state |
| `Controller` | `core/controller.py` | Bus subscriber, routes events to services |
| `DiagnosticsService` | `application/diagnostics_service.py` | `hallptz status`/`hallptz doctor` |
| `BackupService` | `application/backup_service.py` | Backup ZIP creation |
| `RestoreService` | `application/restore_service.py` | Backup ZIP restore |
| `LayoutService` | `application/layout_service.py` | Room layout load/save |
| `FlightRecorder` | `application/flight_recorder.py` | Production blackbox log |
| `RuntimePathResolver` | `runtime/path_resolver.py` | Single source of runtime paths |
| `AppContext` | `core/app_context.py` | Container passed to `MainWindow` |

---

## Before finishing

Run the checks that apply to the change:

```bash
# Always
python3 -m pytest
python3 -m ruff check .
```

```bash
# For architecture/import changes
python3 -m pytest tests/test_architecture_boundaries.py
```

```bash
# For runtime, config, diagnostics, CLI, support or data path changes
python3 -m runtime.cli version
python3 -m runtime.cli status
python3 -m runtime.cli doctor
```

```bash
# For demo/simulation changes
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
python3 -m runtime.cli --profile demo demo reset
```

```bash
# For backup/restore changes (test data only — never real customer ZIPs)
python3 -m runtime.cli backup
python3 -m runtime.cli restore path/to/test-backup.zip
```

For changes touching startup, config, cameras, simulation, UI, installer, systemd, backup/restore or deployment, add the relevant manual check result to the PR body.

---

## Definition of Done (short form)

A task is done when:

- Code/docs change is complete and scoped to the issue.
- Tests added, or PR explains why not applicable.
- `python3 -m pytest` passes.
- `python3 -m ruff check .` passes.
- Normal and demo startup not broken (check if touched).
- `hallptz doctor`/`hallptz status` considered for runtime/config/diagnostics changes.
- README or docs updated when behaviour, setup or operation changes.
- No secrets, customer config or sensitive data committed.
- No new business logic in legacy Qt controllers.
- Migration and recovery considered for config/data changes.
- Backup and rollback safety considered for installer/restore changes.

Full checklist: `docs/DEFINITION_OF_DONE.md`.

---

## Current priority

Default order for Claude Code work:

1. Stabilise release-candidate state and documentation/backlog alignment.
2. Runtime/customer data separation from application code.
3. Persistent production logging.
4. Sanitized support bundle export (#27).
5. Seat ID / label / preset / camera role decoupling.
6. Render seat UI fully from persistent `room_layout.json`.
7. Session start/end/home fully through `SessionService`.
8. Offline signed licensing foundation.
9. Visual editor and advanced product features after foundations are safe.

Release gate issues: Pi validation (#381), pre-RC checklist (#520), support bundle (#27), MVP scope (#288).

---

## Final response format after coding

Report:

1. Files changed.
2. Behaviour changed.
3. Tests/checks run.
4. Risks or manual checks still needed.
5. Data/backup/rollback impact if relevant.
6. Suggested next issue.

---

## Key docs reference

| Doc | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | Layer rules and forbidden imports |
| `docs/ARCHITECTURE_DECISIONS.md` | Formal ADRs |
| `docs/COMMAND_EVENT_POLICY.md` | When to use commands vs events |
| `docs/LIFECYCLE_CONTRACT.md` | Startup/shutdown order and ownership |
| `docs/RUNTIME_PATH_CONTRACT.md` | Path layout, ownership and migration |
| `docs/DEFINITION_OF_DONE.md` | Full DoD checklist |
| `docs/RELEASE_CHECKLIST.md` | Pre-release/install safety checklist |
| `docs/ROADMAP.md` | Delivery phases and MVP status |
| `docs/BACKUP_RESTORE_CONTRACT.md` | Backup/restore safety rules |
| `docs/STATE_OWNERSHIP_AUDIT.md` | Where each piece of state lives |
