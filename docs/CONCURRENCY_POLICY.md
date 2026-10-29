# Concurrency and Threading Policy

**Issue:** #798  
**Epic:** #787 — Establish single source of truth for runtime state  
**Status:** Adopted — applies to RuntimeSafetyService and RuntimeStateStore.

---

## Overview

Hall PTZ Control is a Qt application with several concurrent execution contexts:

| Context | What runs there |
|---|---|
| Qt main thread | UI widgets, `AsyncEventBus` delivery, `ApplicationController`, `Controller`, `SafetyResetService` |
| Camera worker threads | `ViscaCameraWorker`, VISCA socket I/O, `CameraStateService` updates |
| ATEM monitor thread | `ATEMMonitor` (QThread), polling loop, `_emit_state()` Qt signal emission |
| Simulator/demo thread | `FakeCameraPort`, `FakeAtemPort` callbacks |

---

## RuntimeStateStore threading rules

### Lock scope

`RuntimeStateStore` uses a single `threading.Lock` (`_lock`) that protects **only the state replacement** inside each `update_*()` method.

The lock is acquired, the new `RuntimeState` is built, the `_state` reference is replaced, the lock is released.  Subscriber callbacks are called **without** holding the lock.

### What this means for callers

| Situation | Rule |
|---|---|
| Calling `update_*()` from any thread | **Safe** — all methods are re-entrant with the lock held. |
| Calling `snapshot()` from any thread | **Safe** — the returned `RuntimeState` is frozen/immutable; no race possible. |
| Subscriber callbacks | **Must be fast and non-blocking** — they run on the calling thread inside `_notify()`. Never call `update_*()` from a subscriber (re-entrancy would deadlock). |
| Caching a snapshot | **Do not cache across event boundaries.** Snapshots become stale immediately after the next mutation. |

### Thread ownership for each update method

| Method | Who calls it | Thread |
|---|---|---|
| `update_session()` | `SessionService.start/end/clear_runtime_state/set_chairman` | Qt main (via `Controller` event handler) |
| `update_camera()` | `CameraStateService._update()` | Camera worker thread |
| `update_atem()` | `ATEMMonitor._emit_state()`, `_poll_loop()` | ATEM monitor thread |
| `begin_safety_reset()` | `SafetyResetService.reset()` | Qt main thread |
| `apply_safety_reset_clean_state()` | `SafetyResetService.reset()` | Qt main thread |
| `update_lifecycle()` | `bootstrap.py` (startup), `Supervisor` | Qt main thread |
| `update_diagnostics()` | Future degraded-mode reporting | Qt main thread |

---

## Safety Reset race prevention

The Safety Reset sequence is:

```
(Qt main) SafetyResetService.reset()
  1. begin_safety_reset()           → RuntimeStateStore.safety_reset_in_progress = True
  2. RuntimeSafetyService.stop_all_cameras()  → STOP commands sent to all workers
  3. SessionService.clear_runtime_state()     → SessionService state cleared
     └─ _store_session_ended()               → RuntimeStateStore.session = {active=False}
  4. apply_safety_reset_clean_state()         → RuntimeStateStore full clean state
```

**Race window:** Between steps 2 and 4, camera worker threads may still be processing a late command response and call `CameraStateService.on_command_succeeded()` → `RuntimeStateStore.update_camera()`.

**Policy:** This is **acceptable** — the late update only writes `movement_state` or `last_error` to the camera entry. `apply_safety_reset_clean_state()` runs *after* all workers have been stopped, so by the time step 4 executes, the workers have either drained or been interrupted.

**No additional lock is required** because:
1. `RuntimeStateStore._lock` serialises the state replacement.
2. `apply_safety_reset_clean_state()` always wins — it runs last in the sequence.
3. The subscriber list sees the final clean state, not an intermediate state.

---

## ATEM callback after Safety Reset

`ATEMMonitor` runs in a `QThread` and calls `_store.update_atem()` from `_poll_loop()`. If a Safety Reset is applied while `_poll_loop()` is running, the sequence is:

```
[ATEM thread]  _poll_loop() → update_atem(program_input=3)
[main thread]  apply_safety_reset_clean_state()  (does NOT clear atem state)
[ATEM thread]  _poll_loop() → update_atem(program_input=2)
```

The ATEM state is **intentionally not cleared** by Safety Reset because:
- ATEM connection and program state are read-only from the app's perspective.
- Clearing it on reset would cause a false "ATEM disconnected" event.
- The ATEM hardware is unaffected by Safety Reset (no commands sent to ATEM during reset).

---

## What is NOT thread-safe

| Item | Risk | Mitigation |
|---|---|---|
| `SystemState` (legacy `core/state.py`) | `pan_speed`/`tilt_speed` written from event bus thread with no lock | Migrate reads to `RuntimeStateStore` (#794); `SystemState` will be deprecated |
| Qt signals across threads | Qt queues cross-thread signals automatically — safe if emitted from QThread | `ATEMMonitor.state_changed` and `program_changed` use Qt's queued connection |
| `AsyncEventBus` delivery | All subscribers called from the emitting thread (may be camera worker) | Subscribers must not call blocking operations |

---

## Summary: rules at a glance

1. **`RuntimeStateStore.update_*()` — callable from any thread.**
2. **`RuntimeStateStore.snapshot()` — callable from any thread.**
3. **Subscriber callbacks run on the caller's thread — keep them fast, never call `update_*()`.**
4. **Do not hold the store lock yourself — all methods are self-contained.**
5. **`apply_safety_reset_clean_state()` is the final step of Safety Reset — always call it last.**
6. **Do not cache snapshots — read a fresh one from `snapshot()` every time.**
