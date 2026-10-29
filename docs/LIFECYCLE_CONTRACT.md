# Application Lifecycle Contract

This document is the authoritative contract for Hall PTZ Control startup and
shutdown ordering.  It describes what happens, who owns each step, and what the
expected behaviour is when things go wrong.

Related documents:
- [`STARTUP_GATE.md`](STARTUP_GATE.md) — UX states (Ready / Warning / Blocked)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — layer rules and forbidden imports
- [`RUNTIME_PATH_CONTRACT.md`](RUNTIME_PATH_CONTRACT.md) — data path ownership
- [`BACKUP_RESTORE_CONTRACT.md`](BACKUP_RESTORE_CONTRACT.md) — backup safety rules

---

## Startup order

Steps must execute in the order shown.  No step may depend on a later step.

| # | Step | Owner | Notes |
|---|------|-------|-------|
| 1 | Resolve runtime paths (`RuntimePathResolver`) | `runtime/path_resolver.py` | Must complete before any config load or log open |
| 2 | Load config / settings (`load_config`) | `config/loader.py` | Reads `config.yaml` from resolved config dir |
| 3 | Validate config and layout manifest | `config/loader.py`, `application/layout_service.py` | Invalid config → Blocked state.  Missing layout → Warning state |
| 4 | Construct `AppContext` (`build_app_context`) | `bootstrap.py` | Constructs the full object graph: `SystemState`, `AsyncEventBus`, services, `Controller`, `ApplicationController` |
| 5 | Start `AsyncEventBus` | `bootstrap.py` → `core/events.py` | Bus starts inside `build_app_context`; daemon thread |
| 6 | Build ports / adapters (no hardware commands yet) | `ViscaCameraAdapter` implements `CameraPort`; `FakeCameraPort` for testing | Constructors must not open sockets or send VISCA commands |
| 7 | Run startup diagnostics | `DiagnosticsService` (future) / `runtime.cli doctor` | Must complete within bounded timeout; failure → Warning or Blocked |
| 8 | Build UI from `AppContext` | `MainWindow` / `SplashScreen` | UI receives `AppContext`; does not construct services |
| 9 | Decide UI readiness state (Ready / Warning / Blocked) | `SplashScreen` / startup gate | Based on diagnostic results; see `STARTUP_GATE.md` |
| 10 | Wait for explicit operator action to start session | `ApplicationController.start_session` via UI | Session MUST NOT start automatically on boot |

---

## Shutdown order

Steps must execute in the order shown.

| # | Step | Owner | Notes |
|---|------|-------|-------|
| 1 | Stop UI timers (QTimer cancel) | `SessionController` / UI layer | Prevents timer callbacks firing during teardown |
| 2 | Stop camera movement (halt any active pan/tilt/zoom) | `CameraPort.stop_all()` via `ViscaCameraAdapter` | Best-effort; must not block shutdown |
| 3 | End or standby session (`SessionService.end` / `notify_ended`) | `SessionService` | Records `SessionEnded` to FlightRecorder before power-off |
| 4 | Flush FlightRecorder (all pending writes complete) | `FlightRecorder` | Append-only; flush is implicit (no internal buffer), but any in-flight `record()` must return |
| 5 | Stop `Supervisor` | `core/supervisor.py` → `Supervisor.stop()` | Joins daemon thread; idempotent |
| 6 | Stop `AsyncEventBus` | `core/events.py` → `AsyncEventBus.stop()` | Joins worker thread; idempotent |
| 7 | Close adapter connections (VISCA sockets, ATEM) | `CameraWorker.stop()`, ATEM adapter | Best-effort socket close; must not raise |

All shutdown steps are idempotent.  Calling `stop()` on a component that was never
started, or calling it twice, must not raise an exception (see
`tests/test_clean_shutdown.py`).

---

## Ownership table

| Responsibility | Current owner | Tracking issue |
|---|---|---|
| Construct `AppContext` | `bootstrap.py` | — |
| Start `AsyncEventBus` | `bootstrap.py` (inside `build_app_context`) | — |
| Open VISCA connections | `ViscaCameraAdapter` / `CameraWorker` | — |
| Startup diagnostics | `DiagnosticsService` (planned) | — |
| Decide UI Ready / Warning / Blocked | `SplashScreen` / startup gate | `STARTUP_GATE.md` |
| Start session (explicit only) | `SessionService` via `ApplicationController` | #684 |
| Session power/home lifecycle | `SessionService.start` / legacy `session_mixin` | #684 |
| Shutdown order coordination | `MainWindow` / `core/supervisor.py` | — |
| Flush FlightRecorder | `FlightRecorder` (implicit on each write) | — |
| Stop Supervisor | `Supervisor.stop()` | — |
| Stop AsyncEventBus | `AsyncEventBus.stop()` | — |
| Close camera sockets | `CameraWorker.stop()` | — |

---

## Failure states at startup

### Config invalid

- Cause: `config.yaml` fails schema validation or is missing required fields.
- Result: UI enters **Blocked** state.
- Required action: show error summary with field/line where possible; offer
  `Restore last known good config` and `Exit`.
- Normal operation must not start with invalid config.

### Camera unavailable

- Cause: one or more cameras do not respond within the bounded startup timeout
  (`CAMERA_STARTUP_TIMEOUT_SECONDS = 10` in `ui/splash_screen.py`).
- Result: UI enters **Warning / Degraded** state.
- Required action: show which camera is missing; offer `Find missing camera`;
  allow `Start with warnings` via explicit operator choice.
- The splash timeout must not freeze the screen (bounded thread join).

### Demo profile active

- Cause: `--profile demo` flag or `sim_mode.is_active()` returns `True`.
- Result: UI shows a **prominent demo banner** (`DEMO MODE - NO REAL HARDWARE COMMANDS`).
- Normal flow continues but every demo-mode session is visually distinct from production.
- Demo validation must not be presented as pilot or customer readiness.

### Layout invalid or missing

- Cause: `room_layout.json` fails to load or contains structural errors.
- Result: UI enters **Warning** state (missing layout) or **Blocked** state
  (invalid layout where the product cannot safely render seats).
- `LayoutService` errors are swallowed in `bootstrap._create_layout_service()` so
  the app always starts; the startup gate is responsible for surfacing the warning.

---

## Current architecture notes

- `ViscaCameraAdapter` owns socket/VISCA details; application services use `CameraPort`.
  `CameraService` has been removed. Architecture migration complete. See `ARCHITECTURE.md`.
- `SessionService.start()` routes through `CameraPort` (`ViscaCameraAdapter`). The legacy Qt
  `session_mixin` path uses `notify_started` / `notify_ended` as a bridge.
  Both paths record `SessionStarted` / `SessionEnded` to the FlightRecorder.
- `Supervisor` is not yet wired into `MainWindow` shutdown.  It is used in isolation
  today and must be added to the shutdown sequence when workers are registered.
- Session must only start via explicit operator action (button press or confirmed
  dialog).  Automatic session start on boot is forbidden.

---

## GUI process ownership (#885)

Which process owns the Qt GUI is chosen at install time with
`install.sh --gui-mode` (also accepted by `install_hallptz_rpi.sh`).
**Exactly one launcher is ever active** — installing either mode removes the
other's launcher, so switching is reversible and cannot produce two GUIs.

| | `system` (default) | `user` |
|---|---|---|
| Unit | `hallptz-control.service` (system) | `hallptz-gui.service` (`systemd --user`) |
| Runs as | `hallptz` service user | the logged-in desktop user |
| Display access | scoped `xhost +SI:localuser:hallptz` helper per login | inherited from the session — nothing to grant |
| Started by | `graphical.target` | XDG autostart → `/usr/local/libexec/hallptz-gui-session` |
| Runtime dirs | `0750 hallptz:hallptz` | `2770 hallptz:hallptz` (group-writable) |

**Why autostart rather than an enabled user unit.** Raspberry Pi OS Bullseye
runs LXDE, which does not reliably activate `graphical-session.target`, so an
enabled unit could simply never start; `default.target` fires for SSH logins
too and would try to run a GUI with no display. The XDG autostart entry is the
dependable "a graphical session just began" signal, and it imports the live
`DISPLAY` / `XAUTHORITY` / `XDG_RUNTIME_DIR` / `DBUS_SESSION_BUS_ADDRESS` into
the user manager before starting the unit. Starting an already-running unit is
a no-op, which is what guarantees one instance per graphical login.

**Data boundary in `user` mode.** The GUI reaches its own runtime data through
membership of the `hallptz` group (the installer already adds the desktop user to
it so the wizard can read `/opt/hallptz`), with the runtime directories setgid so
new files stay in that group.

Directory permissions alone are not sufficient. JSON data is written atomically
via `tempfile.mkstemp`, which always creates `0600`, and `os.replace` preserves
that — so a file is readable only by whoever wrote it. With two identities
sharing `/var/lib/hallptz` that breaks in both directions: the GUI cannot read what
the service wrote, and `hallptz doctor` / `hallptz backup` cannot read what the GUI
wrote. `core/json_io.py` therefore mirrors the directory's intent onto the file
— `0660` when the directory is group-writable, untouched (`0600`) otherwise, so
system mode is not widened — and `install.sh --gui-mode user` relaxes the files
already on disk, which would otherwise leave the GUI starting with no presets,
seats or layout. Application code stays `0750 root:hallptz` — readable,
never writable — and config writes still go through the provisioning channel.
The boundary is group membership, not root.

`system` remains the default until the merged fixes are accepted on the physical
appliance (#890); `user` is the durable architecture #885 asks for.
`rollback.sh` re-deploys in the recorded mode (`HALLPTZ_GUI_MODE` in
`/etc/hallptz/install-state.env`), so reverting never silently changes ownership.

**Every component reads the mode through `scripts/lib/install_state.sh`.**
This is not stylistic. The wizard's provisioning chain
(`hallptz-provision.service` → `provision_with_rpi_integration.sh` →
`repair_rpi_runtime.sh`) runs on *every* install, and it used to
`systemctl enable hallptz-control` unconditionally — so completing the wizard on a
session-owned install silently re-armed a second launcher and the next boot
opened two GUIs on the same cameras. A component that activates a launcher
without consulting the mode is a bug, and `tests/test_gui_mode_consistency.py`
enforces that. The shared reader always resolves to `system` for a missing,
unreadable or unrecognised value: installs predating the flag were all system
mode, and guessing `user` would disable the only launcher such a machine has.

---

## Invariants

These must hold at all times and must not be broken by any PR:

1. `build_app_context()` is the only place that constructs `SystemState`,
   `AsyncEventBus`, `PresetService`, `ViscaCameraAdapter`, `SessionService` and
   `Controller`.
2. No service constructor may send hardware commands or open network connections.
3. `SessionService.active` is `False` immediately after `build_app_context()`.
4. All `stop()` methods must be idempotent (safe to call before start and twice).
5. FlightRecorder failures must never block or raise into calling code.
6. Shutdown must complete without hanging even if a timer was pending at the
   moment `stop()` was called.

---

## Test coverage

| Test file | What it covers |
|---|---|
| `tests/test_clean_shutdown.py` | Supervisor, AsyncEventBus and CameraWorker stop idempotency |
| `tests/test_startup_smoke.py` | bootstrap → AppContext construction and bus lifecycle |
| `tests/test_splash_startup_sequence.py` | Camera startup sequencing and degraded-mode timeout in SplashScreen |
| `tests/test_lifecycle_contract.py` | Shutdown-during-startup-timer safety; session not active at boot |
