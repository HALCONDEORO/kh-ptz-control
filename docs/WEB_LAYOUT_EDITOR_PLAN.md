# Web layout editor, staged delivery

## Phase 1: isolated editor sandbox

Status: review candidate. No production activation, no LAN listener, no camera commands.
Parent: owner request on 23 November 2026 to use one web editor on the hall screen and laptop.
Depends on: existing layout persistence and schema1. No new runtime dependencies. POSIX-only (fcntl, O_NOFOLLOW, O_DIRECTORY).
Python3.9 syntax compatibility is intended but has not been executed on3.9 here;
local tests ran on3.10. Hardware validation on supported3.9/3.11remains required.
Related: later admin/session integration and seat identity separation.
Risk: medium for future integration, low for existing runtime because it is never imported at startup.

Acceptance checks:
- Generate rows with aisle-separated groups, add/remove/move/relabel/lock seats, undo/redo.
- One browser tab owns an expiring editing turn. Other tabs/browsers cannot save.
- Save uses a content revision; stale versions are rejected, not merged automatically. Integer-only x/y are enforced, and a
confirmed save returns the canonical document (including row/column) to the UI.
- Previous exact bytes retained in history before atomic save via LayoutService.
- Reload sees saved data; corrupt files produce an error, never automatic replacement.
- Loopback only, no service installation, no camera imports and no live data adoption.

Run manually using a NEW empty test directory:

```sh
python -m runtime.web_layout_editor --sandbox /tmp/kh-layout-sandbox --port 8765
```

Open the printed loopback URL in a browser on the same computer. The sandbox owns a
process lock and refuses nonempty directories without its own marker. Do not put its
marker in a customer data directory. Markers have exact versioned content and
links/special files in ancestors or nested history are rejected. These are safety
checks for accidental misuse, NOT a hostile local filesystem isolation boundary;
a malicious local process can still race directory changes. Use only trusted,
user-owned test directories. Runtime environment data paths are not used.

This phase is NOT a supported customer server. Connections have a2second header/body deadline and at most8workers.
Session cookies expire after30minutes idle and are purged on access.
Cookies identify browser sessions,
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
Renewal requires the current unexpired generation; expired turns are never
reacquired by the heartbeat. A lost turn or revision conflict preserves the in-memory draft and reports an error.
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

Browser requests abort after6seconds. Default readable-seat zoom maintains about36px seat targets with internal scrolling; Fit overview deliberately trades target size for overview.

## Phase 2a: authenticated HTTPS local-network sandbox

An explicit, opt-in adapter is available as `runtime.web_layout_editor_lan`.
It still uses a separate synthetic folder and does NOT edit the live hall file.
It requires an existing dedicated administrator credential, a certificate/key
provided by the installer, and a specific private IPv4 interface. No wildcard
listener, port forwarding, firewall modification, automatic certificate creation,
public DNS endpoint or service installation is performed.

```sh
python -m runtime.web_layout_editor_lan --sandbox /tmp/kh-editor-lan-test \
  --bind 192.168.1.20 --port 8766 --certificate /path/server.pem \
  --private-key /path/server-key.pem
```

The address above is an example, not a discovered address for any installation.
Certificate trust must be configured normally on both browsers, with the actual
address/name covered by its SAN. Never disable certificate validation for use.
The implementation enforces TLS1.2or newer. The administrator verifier is the same
fail-closed service used by the camera application; user-mode installations whose
admin verifier is unavailable remain unavailable, without bypass. A global limit
of5sign-in attempts per minute and15minute idle authenticated sessions applies. Reads, save/lease renewal and background
polling do not refresh authentication. A separate activity endpoint is called only
from trusted keyboard/pointer events, at most once a minute; this is a UI idle
policy, not proof of human presence against an authenticated malicious client.

Authentication gates layout reads and every editor mutation. Cookies are HttpOnly,
SameSite=Strict and Secure over HTTPS; each tab still owns its separate writer
lease. TLS handshakes run under the same bounded-worker/deadline policy rather
than blocking acceptance of other requests.

This is not customer deployment readiness. Remaining gates include integration
with the operator process, safe session exclusion, live seat identity/presets,
trusted certificates on real equipment, an administrator-only entry in Qt and
installation/rollback/hardware tests. Do not proxy the unauthenticated loopback
prototype to make it reachable remotely.

Authenticated HTTPS test mode clears the local draft, history, selection and rendered
layout when authentication expires or the user signs out. Unsaved edits are discarded
on expiry. State checks run every five seconds even while editing. Cookie-restored
login shows Sign out; loopback mode shows neither authentication control.

## Native editor comparison sandbox

An isolated native Qt dialog uses the exact same WebLayoutEditor object as the
optional HTTPS adapter. There is one workspace lock, master file, backup history,
revision and writer lease, not two files synchronized after editing. Launch:

```
python -m runtime.native_layout_editor --sandbox /path/to/new-empty-test-folder
```

To compare simultaneous native/web clients, append the same explicit --bind,
--port, --certificate and --private-key parameters used by the HTTPS sandbox.
The web side still requires the configured dedicated administrator credential.
The native comparison launcher is a local synthetic-only test utility, not an
admin-gated operator menu or supported installation. Do not add it to operator
startup or point it at live hall data.

Native controls cover row-block generation (4-6-4 with adjustable row count),
add/delete/drag/relabel/lock, undo/redo, readable scale, shared save and explicit
writer release. Read-only native views refresh every five seconds. It deliberately
does not offer camera memory allocation, production apply, camera control, custom
aisle patterns, keyboard movement or a completed technician settings entry.
Existing session, certificate, physical-device, supported-runtime and installation
acceptance gates remain open. Unsaved native drafts exist only in memory.
