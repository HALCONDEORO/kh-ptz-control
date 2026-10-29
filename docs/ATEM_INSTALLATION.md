# ATEM Installation, Troubleshooting and Handover (#556)

## Overview

Phase 1 Hall PTZ Control ATEM support is **read-only monitoring + manual admin switching only**.
Automatic ATEM switching is **disabled by default** and must not be enabled without validated safety testing.

Camera PTZ control works whether ATEM is online or offline.

---

## Prerequisites

| Requirement | Details |
|---|---|
| ATEM model | BlackMagic Design ATEM Mini / Mini Pro / Mini ISO (validated models — see validation report) |
| Network | ATEM and Raspberry Pi on the same AV subnet (e.g. 192.168.30.0/24). Static IPs required. |
| PyATEMMax | Optional Python dependency — required for production real-hardware monitoring. Not needed for demo/simulation. |
| Firmware | See `docs/ATEM_VALIDATION_REPORT.md` for tested firmware version |
| HALLPTZ version | ≥ 3.38.2 |

---

## Canonical Config (`config.yaml`)

```yaml
atem:
  ip: 192.168.30.100        # ATEM IP address
  installed: true           # ATEM physically connected to network
  enabled: true             # Active monitoring enabled
  disabled_reason: ""       # Set if temporarily disabled
  me_index: 0               # M/E bank index (0 = M/E 1, 1 = M/E 2)
  input_labels:
    1: Platform
    2: Comments
    3: Chairman
    4: None
  connect_timeout_secs: 10
  reconnect_timeout_secs: 30
  automation_disabled: true  # MUST remain true in Phase 1
```

### Validation rules
- `installed: false + enabled: true` → config rejected at startup.
- `installed: true` alone does not open a connection.
- `enabled: true` activates monitoring.
- `automation_disabled: true` **must** remain set in Phase 1. Never change without safety review.

---

## Network and Environment

- Use a dedicated AV VLAN for ATEM and PTZ cameras.
- ATEM IP must be reachable from the Pi: `ping <atem_ip>`.
- No internet required.
- ATEM Software Control may coexist — see validation report for tested coexistence.

---

## Installation Steps

1. Connect ATEM to AV network. Assign a static IP.
2. Set `atem.ip` in `/etc/hallptz/config.yaml`.
3. Set `atem.installed: true` and `atem.enabled: true`.
4. Set `atem.input_labels` to match physical input wiring.
5. Run `hallptz doctor` — check ATEM row shows OK.
6. Record results in `docs/ATEM_VALIDATION_REPORT.md`.

---

## Handover Fields

Record at install handover:

| Field | Value |
|---|---|
| ATEM model | |
| ATEM firmware version | |
| IP address | |
| M/E bank index | |
| Input 1 label | |
| Input 2 label | |
| Input 3 label | |
| Input 4 label | |
| PyATEMMax version (if used) | |
| Test result | PASS / PASS WITH LIMITATIONS / FAIL |
| Tested by | |
| Date | |

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `hallptz doctor` ATEM row: WARNING | ATEM IP unreachable | Check network, ping ATEM, check config.yaml |
| "ATEM disconnected" in UI | ATEM off or wrong IP | Power-cycle ATEM, verify `atem.ip` |
| `atem.enabled=true requires atem.installed=true` | Config mismatch | Set `installed: true` or `enabled: false` |
| CUT/AUTO greyed out in admin panel | Not TECHNICIAN role | Switch to admin/technician mode |
| Camera controls unavailable | Session not started | ATEM state does not block PTZ — check session |

---

## Disabled / Degraded Behaviour

- Camera PTZ control is **unaffected** by ATEM state.
- Degraded wording: **"ATEM unavailable — camera controls unaffected"**.
- `hallptz doctor` ATEM row: `WARNING` (not `ERROR`) when disconnected.
- `hallptz status` omits ATEM section when `installed: false`.

---

## Firmware / Software Update Policy

Any change to ATEM firmware or PyATEMMax version requires:

1. Re-run ATEM hardware smoke matrix (see `docs/ATEM_VALIDATION_REPORT.md`).
2. Update validation report with new version and date.
3. Do not claim customer-ready status until revalidation passes.

---

## Brand / Legal Wording

*ATEM is a registered trademark of Blackmagic Design Pty. Ltd.*
*Hall PTZ Control is not affiliated with or endorsed by Blackmagic Design.*
