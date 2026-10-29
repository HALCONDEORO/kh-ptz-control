# ATEM Auto-Preview Architecture — Future Design (#558)

**Status: DESIGN ONLY — no automation code is enabled.**

This document describes the intended architecture for a future opt-in ATEM
auto-preview feature (Phase 2+).  Phase 1 manual-only controls must not be
changed until all safety gates below are met.

---

## Phase 1 Invariants (must remain intact)

1. `automation_disabled: true` in config — the enforced default.
2. Seat/preset CALL/SET actions do **not** trigger ATEM Preview, CUT or AUTO.
3. Startup and reconnect do **not** trigger CUT or AUTO.
4. CUT and AUTO require explicit TECHNICIAN action — never automated.
5. External ATEM changes (Program/Preview) are read-only state updates only.

---

## Future Auto-Preview Event Boundary

When auto-preview is eventually enabled, the event flow MUST be:

```
SEAT_SELECTED event
  → AutoPreviewPolicy (evaluates: enabled, role, session, cooldown, input mapping)
  → IF approved: AtemCommandService.set_preview(input_id, role=SYSTEM_AUTOMATION)
  → NOT: cut() or auto() — those remain manual-only
```

Key design decisions:
- Only `set_preview` may be automated — never `cut()` or `auto()`.
- Auto-preview requires a new `SYSTEM_AUTOMATION` policy context.
- Policy must be session-aware (blocked when no active session).
- A cooldown/debounce window prevents rapid preview thrashing.
- Auto-preview must be explicitly opted into via config — off by default.

---

## Why Auto-CUT is Prohibited

CUT changes the live on-air signal.  Automatic CUT would risk:
- Unexpected on-air transitions from system glitches or operator mistakes.
- No human review of transition timing.
- Difficult recovery from unintended cuts.

Auto-CUT remains prohibited and requires a separate safety review with
customer/operator sign-off and legal consultation before it can be considered.

---

## Required Safety Gates Before Auto-Preview

- [ ] Hardware validation report passes (`docs/ATEM_VALIDATION_REPORT.md`).
- [ ] `automation_disabled: false` requires explicit config change with warning.
- [ ] `auto_preview_enabled: true` as a separate, independent config flag.
- [ ] `AutoPreviewPolicy` with session guard, cooldown and role check implemented.
- [ ] Full regression test suite for auto-preview path.
- [ ] Customer/operator sign-off on auto-preview risks.
- [ ] `khptz doctor` check explicitly reports automation state.
- [ ] Support bundle captures automation enabled/disabled state.
- [ ] Rollback path documented in case of unintended on-air events.

---

## Config Shape (future — do not implement yet)

```yaml
atem:
  automation_disabled: false          # explicit opt-out of Phase 1 safety
  auto_preview_enabled: false         # second gate — default off
  auto_preview_seat_mapping:
    seat_1: 1   # ATEM input_id for Platform seat
    seat_2: 2   # ATEM input_id for Comments seat
  auto_preview_cooldown_secs: 2
  auto_cut_disabled: true             # must remain true — auto-cut never enabled
```

Both `automation_disabled: false` AND `auto_preview_enabled: true` are required
to activate any automated behaviour.  One flag alone is not sufficient.

---

## No Customer-Facing Automation Claim

Phase 1 documentation and marketing must **not** claim automatic ATEM switching
until all safety gates above are met and validated.

Acceptable wording:
> "Manual ATEM control for admin/support.
> Automatic preview switching available in a future update after safety validation."
