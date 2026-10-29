# MVP Hardware Validation Report — Runtime Safety

> Fill in this template when running the smoke matrix on Raspberry Pi + real hardware.
> Reference: issue #785 / epic #778.

---

## Hardware under test

| Field | Value |
|---|---|
| Date | |
| App version | |
| Raspberry Pi model | |
| Camera model | |
| ATEM model / substitute | |
| Tester | |

---

## Smoke matrix

| # | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| 1 | App starts on Raspberry Pi | App opens without error | | |
| 2 | Camera connects | Camera shows Connected status | | |
| 3 | Start movement → press STOP | Camera stops moving | | |
| 4 | Queue movement → press STOP ALL | All cameras stop | | |
| 5 | Start session → queue movement/preset → Safety Reset | Session inactive, app still usable | | |
| 6 | Safety Reset run twice (idempotency) | No crash, system in known-good state | | |
| 7 | Disconnect camera network → STOP ALL → Safety Reset | App does not crash, errors reported cleanly | | |
| 8 | ATEM path: Safety Reset clears transient state | No destructive ATEM command sent | | |
| 9 | Close app — "Salir sin apagar cámaras" | App closes, no standby/power-off sent | | |
| 10 | Close app — "Salir y apagar cámaras" | App closes, cameras go to standby | | |

### Results key: PASS / FAIL / SKIP (hardware not available)

---

## Failures

> List any FAIL results with follow-up issue numbers.

| # | Description | Follow-up issue |
|---|---|---|
| | | |

---

## Sign-off

Validated by: _______________  
Date: _______________  
Ticket closed: #785
