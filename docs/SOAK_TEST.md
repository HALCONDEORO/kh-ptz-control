# Soak Test Checklist — Real-World Day-Run

Run this checklist before first paid/customer deployment and before major releases.
Target window: **3–4 hours of continuous real-operation simulation**, or a shorter
pilot window (minimum 1 hour) when full soak is not practical.

## Prerequisites

- System running on Raspberry Pi (not dev workstation).
- Both PTZ cameras powered and networked.
- ATEM switcher connected (or mark "ATEM absent" in results).
- Operator using physical touchscreen, not remote desktop.
- Logging enabled: `logs/` directory writable, log level INFO or DEBUG.

---

## Phase 1 — Startup (≈5 min)

- [ ] Boot Raspberry Pi and wait for splash screen.
- [ ] Confirm both camera cards show OK on splash (or note which are degraded).
- [ ] Confirm splash disappears within 10–15 seconds (no infinite hang).
- [ ] Log in with correct operator password.
- [ ] Verify main window loads; session status shows OFF.

---

## Phase 2 — Session Start (≈2 min)

- [ ] Press Start Session.
- [ ] Confirm UI stays responsive during 8-second motor wait (button disabled, not frozen).
- [ ] Confirm both cameras move to Home after 8 seconds.
- [ ] Confirm session status changes to ON.
- [ ] Note any camera error or timeout in logs.

---

## Phase 3 — Core Operation (≈90 min continuous)

Perform each action at least 5 times spread across the session window.

### Preset Recalls

- [ ] Recall presets for 5+ different names.
- [ ] Recall generic Chairman preset (no assigned name).
- [ ] Rapid successive preset recalls (3 in <5 seconds) — no crash or queue overflow.

### Joystick Movement

- [ ] Pan left and right on Camera 1.
- [ ] Tilt up and down on Camera 1.
- [ ] Pan and tilt Camera 2.
- [ ] Press STOP during active movement — confirm camera stops promptly.
- [ ] Move joystick while switching active camera (Cam1 → Cam2) — no stuck movement.

### Zoom

- [ ] Zoom in and out on Camera 1.
- [ ] Zoom in and out on Camera 2.
- [ ] Release zoom during movement — confirm no drift.

### Camera Switch

- [ ] Switch between Platform (Cam1) and Comments (Cam2) buttons multiple times.
- [ ] Confirm zoom slider syncs correctly on each switch.

### Name List Reorder

- [ ] Drag and drop at least 3 names to different positions in the names list.
- [ ] Drag to end of list — confirm appended correctly.
- [ ] Drag upward in list — confirm order correct.

---

## Phase 4 — ATEM Scenarios (if available, ≈15 min)

- [ ] Disconnect ATEM network cable mid-session — confirm no crash; reconnection attempted.
- [ ] Reconnect ATEM cable — confirm switcher resumes normal operation.
- [ ] Run without ATEM configured — confirm app starts without ATEM error dialog.

---

## Phase 5 — Recovery Scenarios (≈20 min)

- [ ] Simulate camera network loss: unplug Cam1 network cable for 30 seconds.
  - [ ] App remains responsive (no UI freeze).
  - [ ] Cam1 commands fail gracefully (logged, not silent).
  - [ ] Reconnect cable — camera recovers without app restart.

- [ ] Restart app cleanly via End Session → close window → relaunch.
  - [ ] Confirm no stale processes or locked files after close.
  - [ ] Confirm new session starts cleanly on relaunch.

- [ ] Simulate hard restart (systemd restart or power-cycle if safe on hardware).
  - [ ] Confirm app restarts automatically via systemd.
  - [ ] Confirm log files preserved after restart.

---

## Phase 6 — End Session (≈2 min)

- [ ] Press End Session button.
- [ ] Confirm confirmation dialog appears.
- [ ] Confirm both cameras enter standby (motors stop).
- [ ] Confirm session status changes to OFF.
- [ ] Confirm UI stays responsive through shutdown.

---

## Phase 7 — Log Review (≈10 min)

After the soak window, review `logs/` for unexpected output:

- [ ] No unhandled Python exceptions (`Traceback` lines).
- [ ] No repeated ERROR or CRITICAL entries (note any that appear).
- [ ] VISCA timeout count within expected range for test conditions.
- [ ] No memory or CPU anomalies during session (check `top` / `htop` if available).

---

## Results Template

Copy and fill in after each soak run:

```
Date:
Duration:
Hardware: RPi version, OS version, camera models
ATEM: connected / absent / simulated

Startup:              PASS / FAIL / DEGRADED — notes:
Session start:        PASS / FAIL — notes:
Preset recalls:       PASS / FAIL — count tested:
Joystick movement:    PASS / FAIL — notes:
Zoom:                 PASS / FAIL — notes:
Camera switch:        PASS / FAIL — notes:
ATEM disconnect:      PASS / FAIL / N/A — notes:
Camera loss recovery: PASS / FAIL — notes:
App restart:          PASS / FAIL — notes:
End session:          PASS / FAIL — notes:
Log review:           PASS / FAIL — exception count: , error count:

Overall result:       PASS / FAIL / CONDITIONAL
Conditional notes:
Tester:
```

---

## Related issues

- #248 — hardware-free startup smoke workflow (prerequisite, now closed)
- #95  — standard network/hardware timeout constants
- #158 — Reconnect Cameras action
- #180 — command latency instrumentation
- #238 — Release safety: tests, smoke checks and CI
