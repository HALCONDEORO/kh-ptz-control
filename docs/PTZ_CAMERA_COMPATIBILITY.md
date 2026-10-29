# PTZ / VISCA Camera Compatibility Matrix

This document records which physical VISCA-over-IP PTZ camera models have been
validated with Hall PTZ Control, and how each model behaves against the
assumptions the application makes.

VISCA-over-IP support is **not** identical across brands and firmware. Without a
recorded matrix, support and sales risk overpromising compatibility. A model is
only `SUPPORTED` once it has been validated against the checklist below, with a
date, commit and hardware record.

Related work: response policy (#697), command queue (#694), Raspberry Pi
hardware validation (#381). This document supplies the real-hardware response
patterns those issues need.

---

## How to use this document

1. Run the [hardware validation checklist](#hardware-validation-checklist)
   against a real camera on a real Raspberry Pi install (or an equivalent test
   bench), following the [safety rules](#safety-rules).
2. Record one row per `vendor / model / firmware` in the
   [compatibility matrix](#compatibility-matrix).
3. Record the ACK/Completion response pattern in the
   [response-pattern notes](#response-pattern-notes) so #697 can rely on real
   data instead of assumptions.
4. Mark a model `SUPPORTED` only with date, commit and hardware evidence.
   Anything else is `UNTESTED`, `PARTIAL` or `UNSUPPORTED`.

> This is a record of evidence, not a promise. Do not claim `SUPPORTED`
> without validation.

---

## Assumptions the application currently makes

These are the defaults baked into the code today (`config/__init__.py`,
`ptz/visca/commands.py`). The matrix exists to confirm or refute them per model.

| Assumption | Current value | Source |
|---|---|---|
| Connection method | VISCA-over-IP, **TCP** | `adapters/visca_camera_adapter.py` |
| VISCA TCP port | `5678` | `config.VISCA_PORT` |
| Connect timeout | `1 s` | `config.CAMERA_CONNECT_TIMEOUT` / `SOCKET_TIMEOUT` |
| Response read timeout | `1 s` | `config.VISCA_READ_TIMEOUT` |
| Confirmed-command success | a terminal frame is required: Completion (`9x 5y FF`) or Error (`9x 6y FF`); ACK alone is **not** success | `ptz/visca/parser.py`, `adapters/visca_camera_adapter.py` |
| Pan speed range | `1`–`24` | `config.PAN_SPEED_MAX` |
| Tilt speed range | `1`–`20` | `config.TILT_SPEED_MAX` |
| Zoom drive range | `1`–`7` | `config.ZOOM_DRIVE_MAX` |
| Preset numbering | `1`–`131`; presets `90`–`99` map to bytes `0x8C`–`0x95`, the rest map directly | `config.PRESET_MAP` |
| Zoom absolute support | assumed (`CAM 010447 pqrs FF`) | `ptz/visca/commands.py:zoom_absolute` |
| Zoom position inquiry | assumed (`CAM 090447 FF`) | `ptz/visca/commands.py:zoom_inquiry` |
| Slow-command warning threshold | `300 ms` | `config.VISCA_SLOW_CMD_MS` |
| Simultaneous TCP connections | the persistent worker keeps one socket; direct inquiry/polling opens additional short-lived sockets | `ptz/visca/worker.py`, `adapters/visca_camera_adapter.py` |

The application does **not** assume PTZ pan/tilt absolute-position inquiry is
supported; preset polling falls back gracefully when it is unavailable. Record
whether a model supports it anyway, because it affects telemetry quality.

---

## Hardware validation checklist

Run on the target hardware. Tick only what you personally observed.

```text
[ ] Camera reachable on TCP port 5678 (or note the real port)
[ ] Power on / standby (CAM 01040002 / 01040003)
[ ] Power inquiry returns a parseable frame (CAM 090400)
[ ] Pan/tilt move at min and max speed
[ ] STOP halts motion promptly (CAM 01060100000303)
[ ] Home (CAM 010604)
[ ] Preset recall across the low (1), mid and high (>89) ranges
[ ] Preset save (on a SCRATCH preset only — never a production preset)
[ ] Zoom drive in / out / stop
[ ] Zoom absolute to a known percentage
[ ] Zoom position inquiry returns a value (CAM 090447)
[ ] PTZ pan/tilt position inquiry — supported? (record yes/no)
[ ] Focus auto / manual (CAM 01043802 / 01043803)
[ ] One-push AF — supported? (record yes/no)
[ ] Exposure / brightness up/down (CAM 01040D02 / 01040D03)
[ ] Backlight on / off (CAM 01043302 / 01043303)
[ ] Response to an UNSUPPORTED command (record the exact frame)
[ ] Behaviour when a 2nd/3rd TCP connection is opened (record the limit)
[ ] Average command round-trip latency (record ms; flag if > 300 ms)
[ ] ACK→Completion timing: same buffer, or separate TCP segments?
```

---

## Compatibility matrix

One row per validated `vendor / model / firmware`. Status legend:
`SUPPORTED` · `PARTIAL` · `UNSUPPORTED` · `UNTESTED`.

| Vendor / model | Firmware | Conn. | Default port | Tested port | Max TCP conns | Power on/standby | Pan/tilt | STOP | Home | Preset recall | Preset save | Zoom abs | Zoom drive | Zoom inq | PTZ pos inq | Focus a/m | One-push AF | Exposure | Backlight | ACK/Completion pattern | Avg latency | Status | Validated by / date | Test environment | Known limitations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| _example: Sony SRG-xxx_ | _e.g. 2.x_ | TCP | 5678 | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | UNTESTED | — | — | — |

> Add rows below. Keep the example row in place as a template.

---

## Response-pattern notes

For each validated model, record the raw response shapes. This is the evidence
#697 (VISCA response policy by command type) depends on.

```text
Model:           <vendor / model / firmware>
Validated:       <date> @ <commit>

ACK only:        <hex>      (e.g. 90 41 FF)
Completion:      <hex>      (e.g. 90 51 FF)
ACK+Completion:  same buffer? yes/no — <hex>
Error frames:    <hex>      (e.g. 90 60 02 FF = syntax error)
Unsupported cmd: <hex>      (what the camera returns for a command it lacks)
Empty/timeout:   <observed behaviour and timing>
Notes:           <delayed completion, malformed frames, ordering, etc.>
```

---

## Safety rules

- Do not run preset **save** against an important production preset — use a
  scratch preset slot.
- Do not test power / standby during a live event.
- Do not claim `SUPPORTED` without a date, commit and hardware record.
- Record unsupported commands clearly; never leave a guessed cell as `SUPPORTED`.
- This document does not change VISCA command behaviour — it records observed
  behaviour only.
