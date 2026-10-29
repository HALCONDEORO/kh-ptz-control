# Architecture Decisions Record

This document captures key architectural boundary decisions for KH PTZ Control.
Each ADR records the context, decision taken and consequences of following that rule.

For product and scope decisions see [`docs/DECISIONS.md`](DECISIONS.md).
For layer rules and forbidden imports see [`docs/ARCHITECTURE.md`](ARCHITECTURE.md).

---

## ADR-001: UI does not call VISCA or hardware directly

**Status:** accepted

**Context:** PTZ cameras are controlled via the VISCA-over-IP protocol. Without a clear boundary, UI widgets could easily grow direct socket calls, making the protocol hard to test, replace or safeguard.

**Decision:** UI code never imports or calls VISCA protocol code, socket code or any hardware adapter directly. All camera intent flows from a UI action through `ApplicationController` and then down through service and adapter layers.

**Consequences:** New UI features must express intent to `ApplicationController`; they must not add socket or VISCA calls. VISCA and socket code stays inside `ptz/visca/` and adapter implementations.

**Issues:** #692

---

## ADR-002: ApplicationController is the UI/application boundary

**Status:** accepted

**Context:** Multiple UI widgets need to trigger product actions (session start, preset recall, camera move). Without a single entry point, each widget risks building its own path to services or hardware, creating duplication and inconsistent error handling.

**Decision:** `ApplicationController` (`core/`) is the single public command API for all UI-originated product actions. UI widgets call only `ApplicationController` methods; they do not call services, ports or adapters directly.

**Consequences:** New product actions must be added as methods on `ApplicationController` before UI can use them. Direct widget-to-service or widget-to-port calls are architecture violations.

**Issues:** #692

---

## ADR-003: SessionService owns the session lifecycle

**Status:** accepted

**Context:** Session start and end involve readiness checks, camera validation, state transitions and potential blocking conditions. Without a clear owner, session logic fragments across the UI, controller and camera code.

**Decision:** `SessionService` (`application/session_service.py`) is the sole owner of session lifecycle: start, end and home. No other layer initiates or terminates a session.

**Consequences:** Session start/end must go through `SessionService`. UI and `ApplicationController` request lifecycle transitions; they do not implement them. Readiness checks and blocking conditions belong in `SessionService`.

**Issues:** #692

---

## ADR-004: CameraPort is the hardware boundary for cameras

**Status:** accepted

**Context:** Application-level camera behaviour (`CameraService`) should not depend on VISCA socket details. As the codebase migrates toward a clean layered architecture, a port abstraction separates application intent from hardware implementation.

**Decision:** `CameraPort` (`ports/camera_port.py`) is the boundary between application services and camera hardware implementations. Application code depends on the port interface; adapters implement it. VISCA and socket details belong in adapters, not in application services.

**Consequences:** New camera hardware integrations implement `CameraPort`. `CameraService` must depend on the port, not on VISCA/socket details. Current `CameraService` socket code is temporary architecture debt to be migrated.

**Issues:** #692

---

## ADR-005: AsyncEventBus reports events; commands are explicit calls

**Status:** accepted

**Context:** `AsyncEventBus` (`core/events.py`) provides a pub/sub channel for notifications. If commands were routed through the event bus, control flow would become implicit and hard to trace or test.

**Decision:** `AsyncEventBus` is used only for events, notifications, diagnostics, logging and integrations. Product commands are always explicit method calls (through `ApplicationController` and services). The bus never carries commands.

**Consequences:** Subscribing to an event must never be the mechanism by which a state change is triggered as a primary command path. Command intent flows through explicit calls; events flow through the bus.

**Issues:** #692

---

## ADR-006: Customer data writes go through services or persistence layer, never widgets

**Status:** accepted

**Context:** UI widgets that write directly to disk or to customer configuration bypass validation, backup hooks and audit trails. This risks data corruption and makes testing harder.

**Decision:** All writes to customer data (configuration, layout, session state, presets) must go through an application service or a dedicated persistence layer. UI widgets must not write files or mutate persistent state directly.

**Consequences:** New UI features that need to persist data must call a service or persistence method. Direct file writes from widget code are architecture violations. Persistence helpers live in `adapters/` or `application/`.

**Issues:** #692

---

## ADR-007: CommandResult is the shared hardware-level result shape; OperationResult (pending) for application level

**Status:** accepted

**Context:** Hardware operations (VISCA calls, camera connection attempts) need a consistent result shape for success, failure and error detail. At the application level a richer shape is needed to convey user-facing messages and recovery hints. Using ad hoc return values or exceptions inconsistently makes error handling fragile.

**Decision:** `CommandResult` (`domain/supportability.py`) is the canonical result shape for hardware-level and low-level adapter operations. `OperationResult` (tracked in issue #689) will be the shape for application-level results. New hardware adapter code must use `CommandResult`; new application service code should await `OperationResult`.

**Consequences:** Ad hoc `(bool, str)` tuples or raw exceptions from hardware code should be replaced with `CommandResult`. Application service return values should migrate to `OperationResult` when #689 is resolved.

**Issues:** #692, #689

---

## ADR-008: The startup/shutdown cycle is explicit and idempotent

**Status:** accepted

**Context:** On a Raspberry Pi appliance that may be power-cycled or restarted unexpectedly, startup and shutdown that rely on implicit ordering or single-call semantics risk leaving the system in an inconsistent state.

**Decision:** Application startup and shutdown sequences are explicit (each step is a named, traceable call) and idempotent (safe to repeat without side effects). Services and adapters must handle being started or stopped more than once without error.

**Consequences:** Service `start()` and `stop()` methods must guard against double-start or double-stop. Startup logging must record each step. Shutdown must not silently skip cleanup steps. Hardware adapters must release resources safely even if stop is called when already stopped.

**Issues:** #692
