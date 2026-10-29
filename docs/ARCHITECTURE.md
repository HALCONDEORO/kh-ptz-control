# Architecture

This document defines the intended architecture boundaries for KH PTZ Control.

The goal is to stop new duplication, keep the codebase installable and make future work safer.

---

## Core rule

New business logic should not be added to legacy PyQt controllers.

Use application/domain services for product logic, and keep UI code focused on presentation and user interaction.

For UI-originated product actions, `ApplicationController` is the public command API. `AsyncEventBus` is for events, notifications, diagnostics, logging and integrations.

Short rule:

```text
ApplicationController commands. EventBus informs.
```

---

## Intended layers

```text
domain/          Pure models, rules and constants
application/     Product use cases and application services
ports/           Interfaces for hardware, storage and external services
adapters/        Implementations for hardware, storage and simulation
ptz/visca/       VISCA protocol details, commands and workers
ui/              PyQt widgets, windows and UI wiring
runtime/         CLI, installer, systemd and diagnostics entry points
bootstrap.py     Application composition / dependency wiring
```

Current code may not fully match this yet. These rules define the target direction for new work and refactors.

---

## Allowed dependency direction

Preferred direction:

```text
ui -> application
application -> domain
application -> ports
adapters -> ports
adapters -> external libraries / hardware
runtime -> application
bootstrap -> all composition dependencies
```

Meaning:

- UI may call application services.
- Application services may use domain models and ports.
- Adapters implement ports and talk to real hardware/storage.
- Runtime commands should call services, not duplicate UI logic.
- Bootstrap is allowed to wire everything together.

---

## Forbidden imports

These imports should not be added in new code:

```text
domain -> PyQt5
domain -> socket
domain -> filesystem reads/writes
application -> PyQt5
ui -> direct VISCA socket commands
ui -> direct JSON persistence
adapters -> ui
```

### Why

- Domain code should be testable without UI, cameras, files or network.
- Application code should not depend on PyQt.
- UI should not own camera protocol, persistence or business rules.
- Hardware/storage code should not know about buttons, windows or widgets.

---

## Layer responsibilities

### `domain/`

Owns pure product concepts.

Examples:

- seat identity
- room layout models
- preset ownership rules
- configuration value objects
- readiness result types

Allowed:

```text
standard library pure logic
simple dataclasses / enums
validation with no side effects
```

Not allowed:

```text
PyQt5
socket calls
file reads/writes
camera commands
logging tied to runtime behaviour
```

---

### `application/`

Owns product use cases and workflows.

Examples:

- camera service
- layout service
- diagnostics service
- backup service
- licensing service
- readiness checks

Allowed:

```text
domain models
ports/interfaces
configuration models
structured result objects
```

Not allowed:

```text
PyQt5 widgets
QTimer/QObject dependencies unless explicitly isolated
hardcoded UI state
raw VISCA socket handling
```

---

### `ports/`

Owns interfaces between application logic and external systems.

Examples:

```text
CameraPort
StoragePort
ClockPort
AtemPort
LicenseStorePort
```

Ports should be small and stable.

---

### `adapters/`

Owns implementations of external systems.

Examples:

- VISCA-over-IP camera adapter
- JSON file storage adapter
- ATEM adapter
- fake/simulation camera adapter
- system diagnostics adapter

Adapters can use external libraries and hardware APIs, but should not import UI.

---

### `ptz/visca/`

Owns low-level VISCA protocol behaviour.

Examples:

- command builders
- command parser
- camera worker
- protocol constants
- transport-specific code

Application/UI code should not duplicate VISCA byte construction.

---

### `ui/`

Owns PyQt interface code.

Examples:

- windows
- widgets
- button states
- visual feedback
- operator interaction

UI should call application services instead of owning product rules.

Bad pattern:

```text
button click -> build VISCA command -> open socket -> write JSON
```

Preferred pattern:

```text
button click -> ApplicationController.recall_seat(seat_id)
```

Current pattern (as implemented):

```text
button click -> ApplicationController.recall_seat(seat_id)
ApplicationController -> CameraPort
ViscaCameraAdapter -> ptz/visca
AsyncEventBus -> status/diagnostic notifications
```

Command routing expectations:

- UI code requests product behaviour through `ApplicationController` or an application service boundary.
- `AsyncEventBus` informs observers and integrations; it should not be the primary command path for camera movement.
- CALL/SET routing should stay behind the application boundary so policy, confirmation and tests are centralised.
- Session start/end ownership should stay in application services such as `SessionService`, not in legacy Qt controllers.
- Runtime adapters should implement ports and own hardware/protocol details.
- Fake adapters should be testable without real cameras, ATEM or Raspberry Pi hardware.

---

### `runtime/`

Owns non-UI entry points.

Examples:

- `khptz version`
- `khptz status`
- `khptz doctor`
- installer helpers
- systemd integration

Runtime commands should reuse application services and not duplicate UI startup logic.

---

### `bootstrap.py`

Owns dependency wiring.

Examples:

- create settings
- create event bus
- create camera manager
- create services
- choose real vs fake adapters
- build `AppContext`

Bootstrap is allowed to know about concrete implementations because it wires the app together.

---

## Correct placement examples

### Example 1 — New diagnostic check

Good:

```text
application/diagnostics_service.py
adapters/system_health.py
runtime/cli.py
```

Bad:

```text
main_window.py
widgets/status_button.py
```

Reason: diagnostics must be callable from CLI without opening PyQt.

---

### Example 2 — New layout validation rule

Good:

```text
domain/room_layout.py
application/layout_service.py
```

Bad:

```text
main_window.py
widgets/go_button.py
```

Reason: layout validity is product logic, not widget logic.

---

### Example 3 — New camera preset recall behaviour

Good:

```text
application/camera_service.py
ptz/visca/*
adapters/camera_adapter.py
```

Bad:

```text
ui/main_window.py builds VISCA bytes directly
```

Reason: UI should request behaviour; VISCA implementation belongs below application layer.

---

### Example 4 — New installer command

Good:

```text
runtime/cli.py
runtime/installer/*
application/diagnostics_service.py
```

Bad:

```text
main.py
main_window.py
```

Reason: installer/runtime behaviour should not require UI startup.

---

## Legacy code rule

The current app still contains legacy Qt controllers and mixed responsibilities.

When touching legacy code:

1. Keep behaviour unchanged unless the issue explicitly changes behaviour.
2. Avoid adding new product logic to legacy controllers.
3. Move new logic into services where practical.
4. Add tests around the new service layer.
5. Leave small adapter calls in UI only when needed during migration.

---

## Known temporary violations

These are known legacy violations and must not be copied into new code:

| File | Violation | Removal path |
|---|---|---|
| `ui/config_dialog.py` | imports `ptz.visca.commands` and calls `_visca._send_cmd` directly | remove when `CameraPort` boundary is complete (#686) |

The architecture boundary test allows this only as an explicit temporary exception (`TEMPORARY_IMPORT_EXCEPTIONS` in `tests/test_architecture_boundaries.py`). The exception budget is capped at 1; adding more violations will fail the guard test.

---

## Architecture tests

Automated import boundary tests exist in `tests/test_architecture_boundaries.py`.

Enforced checks:

```text
application/ must not import PyQt5
domain/ must not import PyQt5
domain/ must not import socket
domain/ must not directly read/write files
ui/ must not import low-level VISCA command builders directly (except documented exceptions)
```

Temporary exceptions are declared in `TEMPORARY_IMPORT_EXCEPTIONS` with a reason and removal issue. The exception budget is enforced; exceeding it fails the test.

---

## Related documents

- `docs/ARCHITECTURE_DECISIONS.md` — formal ADR entries for each boundary decision.
- `docs/COMMAND_EVENT_POLICY.md` — command vs event policy with workflow table.
- `docs/LIFECYCLE_CONTRACT.md` — startup/shutdown order, ownership and invariants.
- `docs/STATE_OWNERSHIP_AUDIT.md` — state duplication map and remediation notes.
- `docs/DECISIONS.md` — product and scope decisions.
- `docs/IMPLEMENTATION_PLAN.md` — practical execution order.

---

## Rule

When unsure where code belongs, choose the layer that can be tested without PyQt, cameras, ATEM or Raspberry Pi-specific hardware.
