# Hall PTZ Control — MVP Dependency Map

This document maps the remaining open issues to their technical dependencies and
gives the recommended implementation order.

**Use this to choose the next implementation PR without guessing.**  
**Authoritative planning context**: `docs/IMPLEMENTATION_PLAN.md`.  
**Confirmed blocker graph**: `docs/ISSUE_BLOCKS_MAP.md`.

Last updated: 2026-05-19. **Archive note (2026-07-02): every issue referenced anywhere
in this document is closed on GitHub** (verified individually, all 59 numbers). This
map's job — sequencing *remaining open* MVP work — is done; it is kept for historical
planning context only. Do not use it to pick the next PR. `docs/ISSUE_BLOCKS_MAP.md` is
the current open-issue snapshot; check that (and `gh issue list`) instead.

---

## Guiding rule

Do not start a later foundation block if it depends on unfinished earlier work.  
Do not promote post-MVP or future issues into the pilot-required set without a
deliberate decision and a recorded rationale.

**Pilot/customer-required** = must be resolved or explicitly accepted before claiming
customer-ready status (see exit criteria in #381 and `docs/IMPLEMENTATION_PLAN.md`).

**Post-MVP** = useful after the first pilot, but does not block claiming that the
system can be installed, diagnosed, backed up and operated.

---

## Dependency groups

### Group 1 — Configuration foundation (P0, pilot-required)

| Issue | Title | Depends on | Status |
|---|---|---|---|
| #443 | Define canonical config.yaml schema and validation | — | ✓ Done |
| #444 | Legacy config migration dry-run and rollback plan | #443 | ✓ Closed |

**Next action**: none — #444 is closed and already reflected as done in the "Recommended
next 10 PR order" table below.

---

### Group 2 — Runtime baseline and deployment contract (P1, pilot-required)

| Issue | Title | Depends on | Status |
|---|---|---|---|
| #450 | Raspberry Pi runtime baseline and compatibility matrix | — | ✓ Done |
| #455 | MVP technical dependency map | — | ✓ Done |
| #381 | Real Raspberry Pi MVP release-candidate validation | All pilot-required foundations | ✓ Closed |

**Next action**: #381 is closed on GitHub. Confirm the pilot/customer-required checklist
below is fully satisfied before treating this as a recorded PASS for release purposes.

---

### Group 3 — Backlog hygiene (P1, continuous)

| Issue | Title | Depends on | Status |
|---|---|---|---|
| #457 | Weekly backlog hygiene recurring checklist | — | ✓ Closed |
| #534 | Weekly normalize open epics | — | ✓ Closed |

**Next action**: none — both closed. If the weekly hygiene process is still wanted going
forward, open a fresh recurring issue rather than reopening these.

---

### Group 4 — Release gate (P2, pilot-required before v0.1.0 tag)

| Issue | Title | Depends on | Status |
|---|---|---|---|
| #452 | Automated release gate | #519, #520, #450 (baseline) | ✓ Closed |

**Next action**: #452 and #381 are both closed on GitHub; re-verify the release gate is
actually wired in CI before relying on this as done.

---

### Group 5 — Runtime/data path separation (P1, pilot-required)

| Issue | Title | Depends on | Status |
|---|---|---|---|
| #499 | Dedicated hallptz user and product directories | #530 | ✓ Closed |
| #530 | Runtime path, ownership and legacy migration contract | — | ✓ Closed |

**Next action**: #530 is closed and already reflected as done in the "Recommended next
10 PR order" table below.

---

### Group 6 — Seat / layout / camera decoupling (P1, post-first-pilot)

| Issue | Title | Depends on | Status |
|---|---|---|---|
| #219 | Seat ID / label / preset / camera role decoupling | #533 | ✓ Closed |
| #533 | Seat model / CameraTargetResolver contract | — | ✓ Closed |

**Next action**: both closed and already reflected as done in the "Recommended next 10
PR order" table below (#650, #651).

---

### Group 7 — ATEM integration (P1, future)

All ATEM issues (#550–#558) are ✓ **closed**.

---

### Group 8 — First-run setup wizard epic (P1, blocked/future)

All first-run wizard issues (#471–#478) are ✓ **closed**. The on-device setup wizard
shipped via PR #867 (`docs/SETUP_WIZARD.md`); Pi hardware QA is tracked separately.

---

### Group 9 — Touchscreen UI (P1/P2, future)

All touchscreen issues (#460–#470) are ✓ **closed**.

---

### Group 10 — Security and privacy (P1, pilot-required)

| Issue | Title | Depends on | Status |
|---|---|---|---|
| #483 | Data privacy, retention and redaction policy | — | ✓ Closed |
| #484 | Supported hardware matrix and installation BOM | — | ✓ Closed |

**Next action**: none — both closed.

---

## Recommended next 10 PR order

Updated 2026-05-19 (reflects PRs #639–#651 merged):

| # | Issue(s) | Work | Pilot-required? |
|---|---|---|---|
| 1 | #443 | Config schema, structured ConfigError, schema doc | ✓ Done |
| 2 | #450, #455 | RPi runtime baseline + dependency map | ✓ Done |
| 3 | #457, #534 | Backlog hygiene first pass | ✓ Done (recurring) |
| 4 | #444 | Legacy migration dry-run and rollback plan | ✓ Done |
| 5 | #530 | Runtime path ownership and legacy data contract | ✓ Done |
| 6 | — | Persistent rotating logs + version in logs (#643) | ✓ Done |
| 7 | #548 | EvidenceSnapshot + support bundle hardening (#644, #645) | ✓ Done |
| 8 | — | SessionService + FlightRecorder session events (#646–#649) | ✓ Done |
| 9 | #219, #533 | Seat/layout decoupling + VISCA resolver wiring (#650, #651) | ✓ Done |
| 10 | #381 | Real Raspberry Pi MVP validation run | ✓ Closed on GitHub — confirm PASS is actually recorded before relying on this |

---

## Pilot/customer-required checklist

Before claiming customer/pilot readiness, confirm:

```text
[ ] #443  Config schema and structured validation — merged
[ ] #450  Raspberry Pi runtime baseline — documented
[ ] #444  Legacy migration dry-run — implemented or explicitly accepted as limitation
[ ] #530  Runtime/data path contract — resolved or accepted
[ ] Persistent logs — working and verified on Pi hardware
[ ] Support bundle — available and redacted
[ ] #381  Real Raspberry Pi validation — issue closed; confirm PASS or PASS WITH LIMITATIONS was actually recorded
[ ] Release checklist (#520) — completed
[ ] Backup/restore — validated on non-customer data on Pi
[ ] Session start/end — validated on Pi
[ ] Starter profile (1 camera) — validated
[ ] Standard profile (2 cameras) — validated
[ ] Demo profile — validated
```

---

## Post-MVP hold list

Do not promote these ahead of pilot-required foundations:

```text
[ ] Full visual layout editor
[ ] Advanced ATEM automation
[ ] Online license validation
[ ] Cloud dashboard
[ ] Multi-room profiles
[ ] Polished guided demo playback
[ ] Touchscreen responsive UI refactor
```

First-run setup wizard shipped (PR #867, Group 8 above) — removed from this hold list.

---

## Separation of future issues from pilot-required

`#381` is closed, so this historical gate no longer blocks anything by itself. The
underlying rule still applies to any *new* future-classified issue: don't start it
ahead of pilot-required foundations without an explicit, recorded promotion decision.

---

*See also: `docs/IMPLEMENTATION_PLAN.md`, `docs/ISSUE_BLOCKS_MAP.md`, `docs/ROADMAP.md`*
