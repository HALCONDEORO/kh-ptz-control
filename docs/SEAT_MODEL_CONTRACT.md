# Seat Model and CameraTargetResolver Contract

Issue: #533.
Parent: #217.
Blocks: #219 (seat decoupling implementation), #535 (CALL/SET contract).
Related: #217, #219, #285, #417, #428, #431, #448, #449, #535.

This document is the canonical contract for the `Seat` model, `CameraTargetResolver`
and layout routing rules. It must be reviewed before implementing seat/preset/
camera-role decoupling across UI and runtime flows.

---

## Problem

Today `seat_id`, visible label, preset and target camera are not independently
modelled. UI code and VISCA mixins can inspect the currently selected camera
button to determine routing, which spreads camera routing logic into the wrong
layer.

---

## Canonical Seat model

The `SeatLayout` dataclass in `domain/room_layout.py` is the canonical seat
record. The legacy `domain/seat.py` `Seat` dataclass is deprecated and should
not be extended.

### Required fields

```text
id            Stable internal string. Format: seat_<zero-padded-number> (e.g. seat_037).
              Must not change when the seat label, preset or position changes.
              Must not be the same as the visible label or the preset number.

label         Operator-facing display string. May be any non-empty string.
              May change without affecting preset or routing.
              Must not be used as a routing key.

preset        Integer VISCA preset number. Range: 0–255 (product limit: 0–63 unless extended).
              Changing a label must not change the preset.
              Changing a position must not change the preset.

camera_role   Routing vocabulary: "platform" | "comments" | (future roles).
              Controls which VISCA connection the seat uses.
              Must not be inferred from the currently selected UI camera button.
              Required field — no default to "whichever camera is active".

x, y          Display position in the rendered room layout (pixels, layout coordinate space).

visible       bool. False = hidden from operator UI. Default: True.

locked        bool. True = cannot be moved or reassigned without explicit admin action.
              Default: False.
```

### Optional fields

```text
row, column   Grid position for structured layouts. May be null.
type          Seat type: "delegate" (default) | "special" | future types.
calibrated    bool. True = preset has been verified against real camera position.
metadata      Optional mapping for future extension. Must not be read by routing logic.
```

---

## camera_role vocabulary

| Value | Meaning | VISCA target |
|---|---|---|
| `"platform"` | Platform camera (e.g. CAM1) | camera configured as CAM1 |
| `"comments"` | Comments camera (e.g. CAM2) | camera configured as CAM2 |

Rules:

```text
camera_role is the stable routing key — not the camera IP, not the camera button state.
Adding a new camera_role requires a product decision and a schema version bump.
An unknown camera_role must not silently fall back to any camera.
An unknown camera_role must produce an error or warning before any camera command.
```

---

## Special seat representation

```text
type: "special" marks a seat button that does not correspond to a delegate.
Examples: "Home", "Emergency Stop", "All Cameras".
Special seats may have no preset or use a sentinel preset value (e.g. -1).
Special seats must not trigger a standard CALL command through CameraTargetResolver.
Special seat actions are handled by their own service or command handler.
```

---

## Stable seat_id format

```text
seat_<zero-padded-number>   e.g. seat_001, seat_037, seat_100
```

Rules:

```text
New seats receive the next available numeric suffix.
Deleted seat IDs must not be reused within the same room_layout.json version.
The seat_id must survive label rename, preset update and position change.
```

---

## Legacy numeric seat mapping

Legacy `seat_names.json` uses bare numeric keys (e.g. `"37": "PersonA"`).

Migration rules:

```text
Numeric key N -> seat_id "seat_<N zero-padded to 3 digits>" when a matching seat exists.
If no matching seat exists for a numeric key: preserve the key in a migration warning log.
  Do not silently delete legacy assignments without an explicit cleanup command.
Migration must not overwrite an existing stable ID that already has a name assigned.
Migration must be idempotent: running it twice must produce the same result.
Migration must record which keys were migrated and which were flagged as unknown.
```

---

## Duplicate preset rules

```text
Two seats with the same preset and the same camera_role: WARNING.
  A warning must identify both seat labels and the shared camera_role.
  The warning does not block save unless the product decision is changed.

Two seats with the same preset across different camera_roles: allowed.
  (Platform seat 5 and Comments seat 5 are independent calibrated positions.)

Protected presets: presets that are assigned to special seats or reserved by the system.
  A protected preset conflict must be caught before save or calibration overwrite.
  The conflict must show: seat label, preset number, camera_role, conflicting seat label.
```

---

## CameraTargetResolver contract

### API

```python
class CameraTargetResolver:
    def resolve(self, seat: SeatLayout) -> CameraTarget:
        ...

    def resolve_by_id(self, seat_id: str, layout: RoomLayout) -> CameraTarget | None:
        ...
```

### CameraTarget shape

```text
camera_role   str  — routing key (passed to the camera service, not to VISCA directly)
preset        int  — preset to recall or overwrite
seat_id       str  — stable identity for audit/log
label         str  — display label for confirmation dialogs and logs
```

### Ownership rules

```text
CameraTargetResolver lives in application/ or domain/ — not in UI.
UI calls the resolver; UI does not inspect camera buttons to determine routing.
CameraTargetResolver must not open sockets or call VISCA directly.
The resolver reads SeatLayout fields — it does not read UI state.
The camera port (CameraPort / ViscaCameraAdapter) receives a CameraTarget and sends the VISCA command.
```

### Error cases

```text
unknown camera_role          -> raise ValueError or return None with a warning
seat not found               -> return None
seat visible=False           -> return None with a warning
seat type="special"          -> return None (special seats are not routed here)
```

---

## UI/service/VISCA ownership boundaries

```text
UI layer (PyQt):
  - Renders seat buttons from room_layout.json.
  - Receives tap/click events from the operator.
  - Calls ApplicationController with a seat_id and action type.
  - Does not decide which camera to move. Does not inspect camera button state to route.

Application layer (ApplicationController):
  - Calls CameraTargetResolver.resolve_by_id().
  - Decides whether the action is allowed via CallSetCommandPolicy (mode, session, hardware).
  - Sends the resolved CameraTarget to CameraPort (ViscaCameraAdapter).
  - Emits domain events (CALL_REQUESTED, CALL_COMPLETED, SET_CONFIRMED, etc.).

VISCA/camera adapter (ViscaCameraAdapter):
  - Receives a concrete command (camera_role + preset) from the application layer.
  - Does not read seat labels, seat IDs or UI state.
```

---

## Follow-up implementation issues

```text
Extend SeatLayout.camera_role to be typed (enum or Literal) in domain/room_layout.py
Add CameraTargetResolver class to application/ or domain/
Add migration helper for legacy numeric seat_names.json keys
Add duplicate-preset warning to layout validation
Add protected-preset conflict check to calibration/save flow
Add tests: resolve, unknown camera_role, duplicate preset, migration
Deprecate and remove domain/seat.py Seat dataclass after migration
Update room_layout.json schema_version
```

---

## Rule

No code path may determine the active VISCA connection by inspecting the
currently selected camera button in the UI.

All camera routing must go through `CameraTargetResolver` → `CameraPort`.
