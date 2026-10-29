# Operator & Support Guide — Safety Actions

This guide explains the four runtime safety actions available in KH PTZ Control.
Knowing which one to use prevents mistakes during a live meeting.

---

## Safety action reference

### STOP

**What it does:** Stops pan/tilt/zoom movement on the currently selected camera.

**When to use:** The camera is moving and you want to stop it without affecting other cameras or the session.

**What it does NOT do:**
- Does not affect other cameras.
- Does not end the session.
- Does not clear any internal state.

---

### STOP ALL

**What it does:** Sends a priority STOP command to every configured camera immediately.

**When to use:**
- All cameras need to stop at the same time (e.g. end of meeting, emergency).
- A camera is stuck moving and you are unsure which one is the problem.

**Guaranteed behaviour:**
- Bypasses the active-session guard — works even with no active session.
- Attempts every camera even if one fails; partial failure is reported.
- Drains queued movement commands so no stale move executes after the stop.

**What it does NOT do:**
- Does not end the session or put cameras into standby.
- Does not clear runtime state.

---

### SAFETY RESET

**What it does:** A full soft runtime reset — stops all cameras, drains command queues, and clears volatile state — **without restarting the app or rebooting the Raspberry Pi.**

**When to use:**
- A session or camera state is stuck and STOP / STOP ALL did not resolve it.
- After a failed command, reconnect glitch, or unexpected state.
- Support asks you to perform a safety reset to return to a known-good state.
- At the end of automated tests to verify no state leaks between runs.

**What is cleared:**
- All camera movement is stopped (priority STOP to every camera).
- Pending command queues are drained.
- Active session state (active flag, chairman name, session ID).
- Session file marker on disk.

**What is preserved (never deleted):**
- `config.yaml` — camera IPs, ATEM address, site configuration.
- `room_layout.json` — seat layout, names, roles.
- Saved presets.
- Licence and installation files.
- Any persistent customer data or logs.

**Idempotent:** calling Safety Reset twice is safe and leaves the system in the same known-good state.

---

### EXIT — Keep cameras on

**What it does:** Closes the KH PTZ Control application without sending a camera standby or power-off command.

**When to use:**
- You need to restart the app but cameras should stay powered and in position.
- You are switching control methods and want cameras ready immediately.

---

### EXIT — Power off cameras

**What it does:** Closes the app and follows the full camera shutdown sequence (standby / power-off).

**When to use:**
- End of day, event done, or cameras need to be put into a low-power state.
- Normal planned shutdown.

---

## Which action to choose?

| Situation | Recommended action |
|---|---|
| One camera is moving, need to stop it | STOP |
| All cameras need to stop immediately | STOP ALL |
| Session state is stuck or corrupted | SAFETY RESET |
| App needs to restart, keep cameras live | EXIT — Keep cameras on |
| End of day, cameras can go to standby | EXIT — Power off cameras |
| Automated test cleanup between runs | SAFETY RESET |

---

## Support: what state is cleared vs preserved

| State | STOP | STOP ALL | SAFETY RESET |
|---|---|---|---|
| Camera movement | One camera | All cameras | All cameras |
| Command queue | Drained for stopped camera | Drained for all | Drained for all |
| Session active flag | No | No | **Cleared** |
| Chairman name | No | No | **Cleared** |
| config.yaml | Never | Never | Never |
| room_layout.json | Never | Never | Never |
| Saved presets | Never | Never | Never |
| Camera standby/power-off | No | No | No |
| App process restarts | No | No | No |
| Raspberry Pi reboots | No | No | No |

---

## Notes for hardware validation

Before claiming runtime safety is pilot-ready, validate on Raspberry Pi + real VISCA camera:

1. App starts on Pi.
2. Camera connects; movement works.
3. Start movement → STOP → camera stops.
4. Queue movement → STOP ALL → all cameras stop.
5. Start session → trigger movement → run Safety Reset → session inactive, app usable.
6. Disconnect camera network → run STOP ALL / Safety Reset → app does not crash.
7. ATEM path: Safety Reset clears transient state without destructive ATEM command.
8. Close with "keep cameras on" → no standby/power-off sent.
9. Close with power-off → existing shutdown behavior preserved.

Record results in `docs/MVP_VALIDATION_REPORT.md` with date, app version, Pi model, camera model.
