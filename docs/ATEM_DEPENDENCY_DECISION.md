# ATEM Commercial Dependency Evaluation and Decision

Issue: #549.
Parent: #545.
Blocks: #550 (ATEM config schema), #551 (AtemPort/FakeAtemPort), #552 (read-only diagnostics).

This document records the evaluation of commercial ATEM library options and the
chosen approach for the first installable Hall PTZ Control ATEM integration.

---

## Evaluated options

### Option A — PyATEMMax (current)

**What it is:** Python library by Claus Schrammel implementing the undocumented
Blackmagic ATEM network protocol. Already in `requirements-atem.txt`.

**Licence:** MIT. Commercial use is permitted. No royalty, no activation requirement.

**Advantages:**
- Already integrated and working in `atem_monitor.py`.
- Graceful degradation: if missing, `atem_monitor.py` disables ATEM monitoring and
  the rest of the application continues.
- `SwitcherPort` / `FakeATEM` abstraction means the concrete dependency is isolated
  behind an adapter — switching libraries later does not require UI changes.
- MIT licence is compatible with proprietary product distribution.
- Actively maintained and used in production AV workflows (community validation).

**Risks:**
- Based on an undocumented Blackmagic protocol — API compatibility on future ATEM
  firmware is not guaranteed.
- Not an official Blackmagic product — no official support channel.
- If Blackmagic changes the protocol in a future firmware, a library update or
  fallback adapter may be required before customer-ready ATEM support is claimed.

**Pinning requirement:** pin to a tested minor version range, e.g. `PyATEMMax>=0.9,<1`.

---

### Option B — pyatem / OpenSwitcher-style integration

**What it is:** Alternative Python implementation. Lower adoption than PyATEMMax
at the time of this evaluation.

**Evaluation:** Not chosen for Phase 1.
The `SwitcherPort` abstraction means switching to pyatem in a future follow-up
would be a contained adapter change, not a product-wide rewrite.

---

### Option C — Node.js sidecar using atem-connection

**What it is:** atem-connection is a well-maintained TypeScript/Node.js library.

**Evaluation:** Not chosen for Phase 1.
Introducing a Node.js sidecar process adds runtime complexity (process management,
IPC, Node.js runtime on Raspberry Pi) that is disproportionate for the Phase 1
manual-only ATEM feature set. The offline-first requirement is harder to guarantee
with a multi-runtime sidecar.

May be reconsidered if PyATEMMax becomes unmaintained or protocol-incompatible.

---

### Option D — Blackmagic official SDK

**What it is:** Blackmagic Design publishes C/C++ SDKs for DeckLink and some
other products; a general Python ATEM SDK is not publicly available at the time
of this evaluation.

**Evaluation:** Not applicable for Phase 1.
No official Blackmagic Python SDK for ATEM network control exists. If an official
SDK becomes available, it should be evaluated before any major Phase 2+ automation
work.

---

## Decision

**Chosen approach: PyATEMMax, kept as optional dependency.**

Rationale:

```text
Already integrated and validated in the codebase.
MIT licence — compatible with proprietary product distribution.
SwitcherPort abstraction isolates it behind an adapter boundary.
Graceful degradation is already implemented (missing library ≠ crash).
Phase 1 scope (manual-only, read + manual-preview) is conservative
  enough that undocumented-protocol risk is acceptable.
```

---

## Licence and commercial risk

```text
Licence:   MIT
Risk:      Low for commercial distribution.
Notice:    PyATEMMax must appear in THIRD_PARTY_ASSETS.md and any
           third-party notice shipped with the product.
Liability: None (MIT). Blackmagic Design is not responsible for
           PyATEMMax and Hall PTZ Control is not an official Blackmagic product.
```

Customer-facing wording (to use in handover docs and product descriptions):

```text
Blackmagic Design and ATEM are third-party products. Hall PTZ Control integrates
with supported and tested ATEM devices using the PyATEMMax open-source library
(MIT licence). Hall PTZ Control is not an official Blackmagic product or partner
unless separately agreed in writing.
```

---

## Approved version and pinning policy

```text
Approved version range:  PyATEMMax>=0.9,<1
Location:                requirements-atem.txt (optional — install only on ATEM sites)
Lock file:               requirements-atem.txt must be pinned before customer installs.
Raspberry Pi install:    pip install -r requirements-atem.txt (only on ATEM-capable sites).
```

Rules:

```text
Do not pin to an exact version in requirements-atem.txt for development use,
  but pin to a tested exact version in any customer install lockfile.
Do not use latest/unpinned PyATEMMax in customer installs.
hallptz doctor must report the installed PyATEMMax version where available.
hallptz doctor must report DEPENDENCY_MISSING (not UNKNOWN) when PyATEMMax is absent.
```

---

## Missing or incompatible dependency behaviour

The current `atem_monitor.py` already implements this:

```text
try:
    import PyATEMMax
except ImportError:
    logger.warning("PyATEMMax not installed — ATEM monitoring disabled")
    return
```

Required behaviour for all code paths:

```text
Missing PyATEMMax:          ATEM state → DEPENDENCY_MISSING
                            PTZ camera control continues unaffected.
                            hallptz doctor reports ATEM DEPENDENCY_MISSING.
                            No crash. No startup gate failure.

Incompatible PyATEMMax:     ATEM state → DEPENDENCY_INCOMPATIBLE
                            Same degraded behaviour as DEPENDENCY_MISSING.
                            hallptz doctor reports version conflict with installed version.

Wrong ATEM firmware:        ATEM state → OFFLINE or ERROR (connection-time failure).
                            Same degraded behaviour. Not a startup-time crash.
```

---

## Fallback and migration path

If PyATEMMax becomes unmaintained or protocol-incompatible:

```text
1. Implement a new adapter class in adapters/ that fulfils SwitcherPort.
2. Update atem_monitor.py to import the new adapter instead of PyATEMMax.
3. Update requirements-atem.txt.
4. Run ATEM hardware validation tests against the new adapter.
5. Update this document with the new decision.
No UI changes are required — the SwitcherPort abstraction isolates the change.
```

---

## Licence notice location

```text
docs/THIRD_PARTY_ASSETS.md — add PyATEMMax entry with version, licence and source URL.
Any product distribution package — include PyATEMMax MIT licence notice.
```

Required THIRD_PARTY_ASSETS.md entry:

```text
| PyATEMMax | >=0.9,<1 | MIT | https://github.com/clvLabs/PyATEMMax |
  Used for optional Blackmagic ATEM network control on equipped sites only.
```

---

## Tested baseline

```text
Library:          PyATEMMax (>=0.9,<1)
ATEM models:      To be recorded per-site during real hardware validation (#557).
ATEM firmware:    To be recorded per-site during real hardware validation (#557).
Blackmagic Software Control: coexistence test required before customer-ready (#557).
```

Real hardware validation must record the exact PyATEMMax version, ATEM model,
ATEM firmware and any incompatibilities found. See issue #557.

---

## Upgrade and revalidation policy

```text
Any PyATEMMax version change requires:
  - Regression test against FakeATEM (automated).
  - Real hardware validation on a test ATEM before customer deployment.
  - An explicit entry in the release checklist noting the version change.
  - An update to the pinned version in any customer lockfile.
  - ATEM firmware updates require revalidation independent of library version.
```

---

## Acceptance criteria

- [x] Commercial dependency approach selected (PyATEMMax, MIT licence)
- [x] Licence and commercial risk documented
- [x] Version/range policy documented (>=0.9,<1)
- [x] Fallback/migration path documented (SwitcherPort adapter swap)
- [x] Licence notice location documented (THIRD_PARTY_ASSETS.md)
- [x] Missing/incompatible dependency behaviour documented
- [x] Update/revalidation policy documented
- [x] No production code changes included
