# Unified CALL/SET Interaction Contract

Issue: #535.
Parent: #286.
Depends on: [Seat Model Contract](SEAT_MODEL_CONTRACT.md) (#533).
Blocks: first installable MVP release until documented and accepted.
Related: #159, #204, #215, #219, #441, #458, #461, #463, #469, #286, #381, #455.

This document is the product-wide contract for CALL and SET behaviour across
all modes, input events and hardware states.

---

## Release rule

Do not declare the first installable MVP release, first pilot release or
customer-ready release until:

```text
This CALL/SET contract is documented, reviewed and either:
  (a) implemented, or
  (b) explicitly accepted as a known limitation with a follow-up issue recorded
      in #381 / docs/MVP_VALIDATION_REPORT.md and a human decision on record.
```

---

## Definitions

```text
CALL    Move a camera to the preset stored for a seat.
        Input: seat_id, camera_role, preset → VISCA recall command.
        Side effect: camera moves. No data is written.

SET     Store the current camera position as the preset for a seat.
        Input: seat_id, camera_role, preset → VISCA store command.
        Side effect: preset is overwritten in camera memory. Data is written.
        SET always requires an explicit confirmed action.
```

---

## Input event mapping

| Input | Normal operator | Admin/installer | Demo | Support | Names | Layout edit |
|---|---|---|---|---|---|---|
| Tap / left click / short press | CALL | CALL | CALL (demo) | blocked | data op | data op |
| Right click / long press | blocked | SET candidate | blocked | blocked | blocked | blocked |
| Keyboard/accessibility activation | CALL | CALL | CALL (demo) | blocked | data op | data op |
| Drag | move not allowed | move not allowed | — | — | allowed (names) | allowed (seats) |

---

## Mode behaviour

### Operator mode

```text
Tap / click = CALL.
CALL sends a real VISCA recall command through ApplicationController → CameraPort → ViscaCameraAdapter.
Right click / long press: blocked. Show clear feedback ("Set preset requires admin mode").
SET is never available to normal operators without mode elevation.
Blocked actions show feedback immediately — no silent failure.
```

### Admin / installer mode

```text
Tap / click = CALL (same as operator mode).
Right click / long press = SET candidate.
SET always requires an explicit confirmation dialog before sending the VISCA store command.
Confirmation must show: seat label, preset number, camera_role, "overwrite?" prompt.
If the operator dismisses the dialog, the command is cancelled. No SET is sent.
SET confirmation must record who confirmed (role: admin/installer) in change_history.
```

### Demo mode

```text
CALL must not move real cameras.
SET must not write real camera presets.
CALL in demo mode updates simulated/fake camera state only.
Demo SET (if implemented) affects demo state only and is clearly labelled as "DEMO".
The demo adapter must intercept all VISCA commands before they reach real sockets.
Accidental demo → real mode transition during a demo session must not trigger pending CALLs.
```

### Support mode

```text
Diagnostics must not move cameras.
CALL is blocked by default in support mode.
CALL may be explicitly enabled if a separate approved calibration/support flow requires it,
  but must be logged as a support action with technician identity.
SET is blocked by default unless an approved calibration flow explicitly enables it.
Support actions must be summarized in the support bundle without raw secrets or IPs.
```

### Names mode

```text
Assigning, editing, moving or clearing names must not trigger CALL.
Assigning, editing, moving or clearing names must not trigger SET.
Seat/name clicks in Names mode are data operations, not camera commands.
Clicking a seat in Names mode assigns or edits the name only.
The application must enforce this at the service layer, not only at the UI layer.
```

### Layout edit mode

```text
Moving seats, editing labels, editing coordinates or selecting seats must not trigger CALL.
Moving seats, editing labels, editing coordinates or selecting seats must not trigger SET.
Preset or camera_role changes in the layout editor do not automatically calibrate the camera.
A deliberate "Calibrate" action (SET) in the layout editor follows the admin/installer SET flow.
```

### Session inactive / no active session

```text
CALL: blocked. A clear session-start UI prompt should appear if appropriate.
SET: blocked. Calibration may be available as a separate admin flow outside sessions.
```

### Camera unavailable / degraded hardware

```text
CALL: blocked for the affected camera_role. Show: "Camera unavailable — check connection."
SET: blocked.
Other camera_role operations should continue if only one camera is unavailable.
Emergency/Home/Stop must not depend on camera availability.
```

---

## Command policy

### CALL is allowed when

```text
mode is operator, admin or installer
session is active
camera_role is available (camera is connected and ready)
the action is not rate-limited by the circuit breaker
```

### SET is allowed when

```text
mode is admin or installer
operator has explicitly confirmed the SET dialog
camera_role is available
no SET is already pending for the same seat
```

### SET requires confirmation when

```text
Always. No SET may bypass the confirmation dialog, even for admin.
Exception: automated calibration in a supervised calibration session (separate flow).
```

### CALL is blocked when

```text
mode is demo (real cameras), support, Names or layout edit
session is inactive
camera unavailable for the target camera_role
```

### SET is blocked when

```text
mode is operator, demo, support, Names or layout edit
no active confirmation dialog
camera unavailable
a live event session is active and the seat is in use
```

---

## User feedback when blocked

```text
CALL blocked in demo mode:     "Demo mode — camera controls simulated."
CALL blocked: no session:      "Start a session to control cameras."
CALL blocked: camera down:     "Camera unavailable — check connection."
CALL blocked: support mode:    "Camera control disabled in support mode."
SET blocked: not admin:        "Set preset requires admin or installer mode."
SET blocked: not confirmed:    <dialog dismissed — no additional message required>
SET blocked: live session:     "Cannot set preset during an active session."
Any blocked action in Names:   No camera feedback shown — Names UI does not show camera state.
```

---

## Service ownership

```text
ApplicationController owns the CALL/SET decision.
  Receives intent from UI (seat_id + action type).
  Calls CameraTargetResolver to resolve camera_role and preset.
  Checks mode, session and hardware availability via CallSetCommandPolicy.
  Returns blocked/allowed/error before sending any VISCA command.
  Logs every CALL and SET attempt (outcome + reason) via CameraPort / FlightRecorder.

UI layer:
  Sends the seat_id and action type.
  Shows the confirmation dialog for SET.
  Shows feedback for blocked actions.
  Does not decide if the action is allowed.

VISCA/camera adapter:
  Executes the VISCA recall (CALL) or store (SET) command.
  Does not read mode, session state or seat labels.
```

---

## Change history

Every CALL and SET attempt must be recorded in `change_history.json`:

```text
CALL:
  at, seat_id, label, camera_role, preset, outcome (success|blocked|error), mode

SET:
  at, seat_id, label, camera_role, preset, outcome, mode, confirmed_by (role)
  Before value: previous preset (if known)
  After value: new preset (same as seat.preset after confirm)
```

---

## Protected presets and rate limits

```text
Protected presets: defined per camera_role by the product config.
  SET to a protected preset must always show an extra warning in the confirmation dialog.

Rate limit for CALL: max 1 CALL per 300 ms per seat (debounced at service layer).
  Rapid taps must not send multiple simultaneous VISCA commands.

Circuit breaker: if a camera fails to respond to 3 consecutive commands, block further
  commands for that camera_role for 5 seconds and show a degraded-mode banner.
```

---

## Acceptance criteria

- [x] CALL and SET defined precisely
- [x] Mode behaviour table for all 6 modes
- [x] Input event mapping for all input types
- [x] CALL/SET allowed/blocked conditions listed
- [x] Confirmation requirement for SET stated (always required)
- [x] Blocked action user feedback defined for each case
- [x] Service/UI/VISCA ownership boundaries stated
- [x] Change history requirements stated
- [x] Protected preset and rate limit rules stated

---

## Follow-up implementation issues

```text
Implement mode-aware CALL/SET guard in ApplicationController / CallSetCommandPolicy
Add SET confirmation dialog to Qt UI (admin/installer mode only)
Add session-active check to ApplicationController.recall_seat() and ApplicationController.set_preset()
Add CALL blocked feedback for degraded camera states
Add demo mode adapter to intercept VISCA commands (FakeCameraPort already covers demo)
Add rate limiter and circuit breaker to ViscaCameraAdapter / CameraPort
Record CALL and SET outcomes in change_history.json
Add tests: CALL in each mode, SET confirmation required, SET blocked in operator mode,
           demo CALL does not reach real socket, Names click does not trigger CALL
```

---

## Rule

No code path may send a real VISCA command without first passing through
the CALL/SET guard in `ApplicationController` / `CameraPort`. There is no fast path from UI to VISCA.
