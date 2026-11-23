# Web layout editor, staged delivery

## Phase 1: isolated editor sandbox

Status: review candidate. No production activation, no LAN listener, no camera commands.
Parent: owner request on 23 November 2026 to use one web editor on the hall screen and laptop.
Depends on: existing layout persistence and schema1. No new runtime dependencies.
Related: later admin/session integration and seat identity separation.
Risk: medium for future integration, low for existing runtime because it is never imported at startup.

Acceptance checks:
- Generate rows with aisle-separated groups, add/remove/move/relabel/lock seats, undo/redo.
- One browser tab owns an expiring editing turn. Other tabs/browsers cannot save.
- Save uses a content revision; stale versions are rejected, not merged automatically.
- Previous exact bytes retained in history before atomic save via LayoutService.
- Reload sees saved data; corrupt files produce an error, never automatic replacement.
- Loopback only, no service installation, no camera imports and no live data adoption.

Run manually using a NEW empty test directory:

```sh
python -m runtime.web_layout_editor --sandbox /tmp/kh-layout-sandbox --port 8765
```

Open the printed loopback URL in a browser on the same computer. The sandbox owns a
process lock and refuses nonempty directories without its own marker. Do not put its
marker in a customer data directory. Runtime environment data paths are not used.

This phase is NOT a supported customer server. Cookies identify browser sessions,
not administrators. There is no user authentication, TLS, rate limiting or LAN
binding. Do not reverse-proxy it, tunnel it or expose it to the local network or
internet. The stdlib HTTP server is used only for this loopback prototype.

The sandbox starts empty. New seats have a UUID, label, position and preset0
(unassigned), calibrated=false. These sandbox files MUST NOT be imported into the
current operator app: preset0 is not a usable camera destination. This intentionally
prevents copying existing physical presets as seats are added. The identity/preset
migration is an acceptance gate for production, not something phase1 claims to solve.

Read-only views refresh the master every5seconds, and before acquiring a turn.
Editing turns renew every25seconds and expire after90seconds without renewal.
A lost turn or revision conflict preserves the in-memory draft and reports an error.
Reload/cancel ask before discarding changes; no offline merge or draft recovery after
a browser crash is provided yet. Undo history lasts only within the current tab.
History snapshots are not automatically pruned in this prototype. Saving geometry
with overlapping seats is allowed in phase1; overlap review/warnings are later gates.

## Phase 2: secure local-network integration

- Replace sandbox session identity with explicit admin authentication, secure local
  transport/access policy, expiry/rate limits, CSRF and host/origin checks.
- One server owns the existing master; no independent GUI/file writer races.
- Open the same editor from the Qt administrator screen and laptop browser.
- Block applying geometry while an operator session is active, including session
  changes during a request. Editing must never dispatch CALL/SET/PTZ.
- Apply validated saved master at a safe boundary, reconcile existing names by stable
  identity. Do not silently change manual camera selection to automatic role routing.
- OS process ownership, resource limits, shutdown, install/package assets and backup
  policy must be reviewed before enabling LAN. No internet port exposure.

## Phase 3: production model and commissioning

- Separate persistent seat identity from label and camera preset in all UI paths.
- Review reserved slots and real per-camera capacity; no guessed preset allocation.
- Versioned migration only when schema additions require it. Exact rollback and old
  operator compatibility checks; no calibrated status inherited across venues.
- Add alignment, multiselection, collision warnings, preview at operator resolution,
  accessible keyboard/touch controls, template import/export and calibration workflow.
- Independent review67must PASS the exact candidate before merge/publication.
- Hardware/installer/rollback tests on a Raspberry Pi before customer activation.

## Verification

Automated tests live in tests/test_web_layout_editor.py. They cover real persistence,
previous-byte backup, exclusive lease/expiry, stale revisions, external updates,
validation, failure/corruption, independent process ownership, host/origin/session
rejection and bounded static routes. Existing layout/architecture tests must pass.
Browser smoke: two isolated sessions, generate84seats (6×(4+6+4)), move one, save,
reload, check previous-byte backup, reject second writer, inspect desktop/mobile.
This is synthetic evidence only, not a real hall, two physical machines or cameras.
