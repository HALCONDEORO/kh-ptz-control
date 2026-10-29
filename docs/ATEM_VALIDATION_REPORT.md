# ATEM Hardware Validation Report (#557)

**Template** — complete one copy per installation or revalidation event.

---

## Environment

| Field | Value |
|---|---|
| Date | |
| Validator | |
| HALLPTZ version | |
| Raspberry Pi model | |
| Raspberry Pi OS version | |
| ATEM model | |
| ATEM firmware version | |
| PyATEMMax version (if used) | |
| Network topology | |

---

## Test Matrix

### Connectivity

| Test | Result | Notes |
|---|---|---|
| Pi can ping ATEM IP | PASS / FAIL / SKIP | |
| ATEM connects on startup (`hallptz doctor`) | PASS / FAIL / SKIP | |
| `hallptz doctor` ATEM row: OK | PASS / FAIL / SKIP | |
| ATEM reconnects after disconnect/reconnect | PASS / FAIL / SKIP | |

### Program / Preview display

| Test | Result | Notes |
|---|---|---|
| Correct input labels shown | PASS / FAIL / SKIP | |
| Program input changes reflected in UI | PASS / FAIL / SKIP | |
| Preview input changes reflected in UI | PASS / FAIL / SKIP | |
| Incorrect mapping shows identifiable mismatch | PASS / FAIL / SKIP | |

### Manual Admin Commands (TECHNICIAN role only)

| Test | Result | Notes |
|---|---|---|
| `set_preview_input` changes ATEM preview bus | PASS / FAIL / SKIP | |
| CUT transitions program correctly | PASS / FAIL / SKIP | |
| AUTO transitions with configured transition effect | PASS / FAIL / SKIP | |
| CUT/AUTO blocked for camera_operator role | PASS / FAIL / SKIP | |
| CUT/AUTO greyed out in UI for non-technician | PASS / FAIL / SKIP | |

### Failure / Degraded

| Test | Result | Notes |
|---|---|---|
| Startup with ATEM disconnected (no hang) | PASS / FAIL / SKIP | |
| Startup with wrong ATEM IP (no hang) | PASS / FAIL / SKIP | |
| Camera PTZ works while ATEM offline | PASS / FAIL | |
| `hallptz doctor` warns (not blocks) on ATEM offline | PASS / FAIL / SKIP | |
| Reconnect after power-cycle | PASS / FAIL / SKIP | |
| ATEM Software Control coexistence | PASS / FAIL / N/A | |

### Automation Safety

| Test | Result | Notes |
|---|---|---|
| CALL preset does NOT trigger ATEM CUT/AUTO | PASS / FAIL | |
| SET preset does NOT trigger ATEM CUT/AUTO | PASS / FAIL | |
| Reconnect does NOT trigger CUT/AUTO | PASS / FAIL | |
| `automation_disabled: true` confirmed in config | PASS / FAIL | |

---

## Summary

| Field | Value |
|---|---|
| Overall result | PASS / PASS WITH LIMITATIONS / FAIL |
| Customer-ready? | YES / NO / NOT YET |
| Blocking issues | |
| Accepted limitations | |
| Next revalidation trigger | firmware update / PyATEMMax update / model change |
