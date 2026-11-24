# Changelog

All notable changes to this project should be documented in this file.

This project uses a simple versioning approach while it is still in early product development:

- Patch version: documentation, tests, install scripts, small fixes.
- Minor version: new features or significant refactors.
- Major version: breaking changes for installation, configuration or customer deployments.

## Unreleased

### Added

- Editable Comments → Home position: holding the Comments → Home button for
  five seconds asks for confirmation and saves the current Comments camera
  framing to a dedicated VISCA preset slot in the camera's own memory. A tap
  recalls the saved position from then on; installs that never save one keep
  the previous mechanical-home behaviour.

## 1.2.4 - release preparation (2026-11-24)

- Add a compact USER camera power toggle with pause/play and two-camera icons,
  pastel state colors, accessible labels and standby-only tooltips.
- Reuse one nonblocking, touch-sized confirmation component for start-up,
  operator power-on and operator standby. Not now is the safe default.
- Keep the standalone PTZ panel self-test independent of session controls.
- No target-Pi acceptance or stable/customer-ready status is implied. See
  [1.2.4 release notes](docs/releases/1.2.4.md) for open release gates.

### Other accumulated changes

### Added

- Add offline user Help through a quiet corner question mark below Admin Mode,
  with eight tutorials, read-only status/version and STOP BOTH CAMERAS without
  confirmation. Reuse the full queued-movement cancellation and runtime STOP
  route, keep the main ADMIN-only STOP ALL button and its permissions unchanged,
  and report delivery separately from unverified physical stopping.

### Changed

- Shorten preset long-press SET to one second for USER and ADMIN. Keep
  confirmation, short-tap CALL and interrupted/drag gesture cancellation.

### Documentation

- Add a short version/symptom/checks support-report checklist, keeping private
  site data out of public issues and physical fallback ahead of reporting.

### Documentation

- Link the live Pages site and sync README/installation guides with the four
  installation stages. Record the active publishing source, ADMIN-only STOP ALL
  rehearsal and USER stopping limits without certifying pending hardware tests.

### Changed

- Show STOP ALL only in ADMIN, including inline role changes. Keep underlying
  stop services and joystick-release stopping unchanged. USER has no separate
  all-camera stop button; document ADMIN rehearsal and a password-free physical
  fallback. Refresh the USER-mode simulation screenshot.

### Changed

- Break website installation into reviewed-build, readiness, install and setup
  stages while preserving every command and its stop/identity checks.

- Put troubleshooting after operation, ahead of optional ATEM and contributor
  architecture details. Keep advanced content in labelled native disclosures.

- Explain the project, room-operator audience and pending hardware validation
  on the first screen. Remove the repeated feature-summary band.

## 1.2.3 - Release candidate

Prepared on 2026-11-14 for operator testing. Target-Pi acceptance and a verified
external pre-update backup remain pending. See `docs/releases/1.2.3.md`.

### Added

- The zoom percentage is marked unconfirmed (dimmed, `ZOOM ?` caption, tooltip)
  from settle until a current camera read confirms it; a failed or silent read
  keeps the mark. No polling was added (#325).

### Changed

- The newest pending preset per camera now supersedes earlier still-pending
  preset requests; an in-flight recall always completes and STOP, session
  boundaries and other events are unchanged (#324).

### Fixed

- Concurrent source-YAML camera configuration saves are serialized with the
  existing per-path transaction lock, so simultaneous saves no longer lose one
  camera's change (#323).

### Known limits

- Only pending (not-yet-started) presets are superseded; an in-flight recall is
  never interrupted mechanically. The unconfirmed zoom mark is not a new camera
  reading. Physical camera behavior remains unverified on the target Pi.
- The published v1.2.1 and v1.2.2 tags and assets remain unchanged.


## 1.2.2 - Release candidate

Prepared on 2026-11-14 for operator testing. Target-Pi acceptance and a verified
external pre-update backup remain pending. See `docs/releases/1.2.2.md`.

### Fixed

- Read observed zoom after the latest absolute-zoom command settles, including
  failure or timeout, instead of leaving the requested target on screen (#321).
- Reject older zoom readbacks after a newer slider intent, and suppress settled
  feedback after session changes, camera changes, shutdown or a newer debounce.

### Known limits

- Preset requests still use the existing FIFO controller path. A later preset
  does not immediately supersede an in-flight recall or discard intermediate
  pending presets. This release does not claim last-preset priority.
- Physical camera behavior, motion interruption and stopping remain unverified
  on the target Raspberry Pi. A failed inquiry cannot establish actual zoom.
- The published v1.2.1 tag and assets remain unchanged.


## 1.2.1 - Release candidate

Prepared for validation on 2026-11-11. Not yet certified on the target Pi.
See `docs/releases/1.2.1.md` for release gates and known limitations.

### Added

- Add a static English project website with installation/operator/support
  routes, a simulation screenshot and manual UI-state walkthrough. Refresh
  README entry points. GitHub Pages activation remains a separate admin step.

- A separate CI contract checks the pinned ATEM library on loopback,
  including its unsupported PiP API without guessing keyer writes.
- Offline camera and panel self-test (`python -m runtime.cli selftest --json`)
  built on the scripted VISCA simulator, run in CI before the unit tests.

### Fixed

- Use body-text ink for the historical video disclaimer so its small text
  meets the 4.5:1 contrast threshold against the walkthrough background.
- Make the website installation instructions select an approved tag or full
  commit SHA in detached HEAD and show the resolved SHA before installation.

- Correct website/README setup scope to room details, camera addresses and
  login settings. Label the older UI walkthrough as historical, captured
  before the current STOP ALL button, rather than showing it as current UI.

- Preserve runtime-directory group-write permissions until session GUI
  quiescence succeeds, so an aborted pre-copy guard does not revoke access
  from a desktop controller that is still running.

- Stop and verify session-owned GUIs in identified live user managers before
  product code replacement, including user-to-system mode changes. Refuse the
  copy if a manager or stop cannot be verified. GUIs stay stopped on success
  or failure; reopen only after a successful install or review of a failure.
  Physical Pi desktop-session validation remains outstanding.
- Clarify operator safety documentation: STOP ALL has a GUI route, Safety
  Reset remains a service contract, and software success does not confirm
  physical stopping. Keep partial-failure and hardware-validation limits clear.

- Exclude exact canonical KHPTZ startup filenames from legacy readiness
  warnings while continuing to detect legacy entries such as hallptz.desktop.

- Recovery redeploy exits with an error instead of announcing completion
  when a provisioned system-mode service stays down after start. This does
  not imply automatic reversion of the redeployed files; the existing bounded
  restart attempt remains unchanged.

- Show unavailable disk-space and Pi-readiness probes as non-blocking
  warnings, not passed checks. Keep manual-check remediation visible.

- Validate ZIP member CRCs before modern restore writes or safety-backup
  creation, in both real and dry-run paths, including old unhashed archives.
  This adds an archive read pass, not disk-failure rollback or complete
  normalization of manifest/decompression errors.

- Reject unrepresentable layout schema versions as failed imports rather
  than raising OverflowError; existing layout and import-backup bytes remain
  unchanged on this validation error.

- Preserve the last valid JSON backup when saving after recovery from a
  corrupt primary. Rotate the primary into `.bak` only when it contains valid
  UTF-8 JSON, including when the final primary replacement later fails.

- Clear absent graphical-session variables from the systemd user manager
  before importing current values and starting the GUI service. Abort if
  clearing fails. This does not validate Pi login behavior or a GUI kept
  alive after logout through linger.

- Network diagnostics no longer use a TCP probe to judge UDP ATEM health.
  The default check reports advisory `not_run` and directs users to the app
  monitor. A healthy ATEM can therefore still show a verification-not-run
  warning; this is not evidence that the switcher is unreachable.

- Disable automatic ATEM discovery and the TCP-based Scan action rather than
  treating TCP reachability as switcher detection. Both buttons remain visible
  but disabled; enter the IP manually and use Reconnect ATEM with monitor status.

- ATEM status and diagnostics use the live library link state instead of
  reporting a stale completed handshake as connected. Preserve the client
  for library-managed reconnection and restore inputs when the link returns.

- Setup device checks show the next remediation step alongside each check
  when it is not already included in the detail text.

- Redact evidence-snapshot notes and collector error text before returning
  or persisting them. Redaction failures use safe placeholders and mark the
  snapshot unclean; structured metadata keeps its existing contract.

- Include runtime endpoint overrides in installation fingerprints. Existing
  baselines with an overlay can show `changed_since_validation` until explicit
  revalidation; baselines are never renewed automatically. Installations
  without an overlay retain their existing config hash.

- Warranty assessment stays UNKNOWN when doctor diagnostics cannot run.
  Support hints request a diagnostic retry rather than falsely claiming
  the validated baseline is missing or encouraging a replacement mark.

- Write known-good and maintenance state through the atomic file writer.
  Contract change: maintenance `mark_complete` raises on disk failure instead
  of returning an unsaved record; the CLI reports failure and exits 1. Newly
  created files use mode 0600, or 0660 with a configured appliance group.

- Refuse known-good marking when the doctor blocker scan cannot run,
  rather than treating a failed scan as an empty blocker list. The explicit
  `--force` override remains available.

- Blocked SET feedback now falls back to the existing admin-entry button
  instead of a missing attribute when the Settings gear is hidden.

- Legacy backup import now validates every recognized JSON/TXT payload before
  writing any files. Contract change: invalid later content no longer leaves
  earlier members partially restored. Existing files and backups stay intact
  on content-validation errors; multi-file I/O failures are not rolled back.

- Fix Settings Access-tab observers accumulating after each dialog closes.

- Test text-source files across the repository for accidental NUL bytes
  after repairing the legacy autostart script.
- The setup review plan scrolls on an 800x480 display while wizard
  navigation buttons remain reachable.
- Starting a seat-name drag cancels its pending long-press preset SET
  so moving a name does not overwrite a camera position.
- Demo guards and diagnostics protect the service production directory
  as well as the legacy user directory.
- PiP writes report network failures as NETWORK_ERROR and keep healthy
  connections open after non-network library errors.
- Demo ATEM controls stay reachable while disconnected so operators can reconnect the virtual switcher.
- Runtime ATEM IP edits start or replace the monitor instead of polling a stale endpoint.
- Legacy backup imports reject duplicate archive member names before
  overwriting current files or their recovery backups.
- Report unsupported ATEM PiP state once instead of failing silently on
  every monitor poll, and expose the unsupported capability.
- Preserve corrupt runtime overlays for diagnosis and allow endpoint updates
  to recover from the base configuration.
- Legacy autostart cleanup uses the intended NUL escape in its process guard.
- Simulated camera moves ignore arrivals superseded by a later recall or stop.
- Warn when a seat rename cannot save its existing camera preset, while
  keeping the in-memory rename available for the next persistence retry.
- Setup keeps watching an unresolved provisioning request after timeout or
  unreadable results and blocks Back until a definitive outcome allows retry.
- Reject backup ZIP archives with duplicate member names before restoring
  files, including dry-run validation.
- Add an always-available STOP ALL button that retires queued camera moves,
  stops configured cameras and shows partial failures without a modal dialog.
- deduplicate repeated PiP feedback before moving cameras.
- keep production PiP state tied to monitor telemetry.
- ATEM monitoring ends a session after thirty consecutive poll failures so
  the supervisor can reconnect, including when the link drops with cached input.
- A disconnected ATEM monitor becomes eligible for a supervisor retry after
  thirty seconds instead of remaining permanently treated as healthy.
- ATEM writes report DISCONNECTED when the underlying link is down instead
  of claiming success for commands the library did not send.
- The setup wizard no longer suggests an address ending in .255 when
  proposing the next camera address in the same subnet.
- Installer mirrors preserve simulation state and saved production endpoints.
- Boot duration metrics use a monotonic clock so wall-clock corrections
  do not corrupt measured startup durations.
- The extracted main-window budget is capped at 1700 lines, below the
  previous 1792-line ceiling, leaving room for approved reconnect safety work.
- VISCA watchdog logic is extracted from the main window with regression
  tests, reducing its size limit without changing the intended behavior.
- Each logging handler receives its own repeat filter so file logs do not
  lose records already seen by the console; startup tests isolate filter state.
- Test setup preloads real Qt and shared UI modules so later tests do not
  inherit partial stubs installed during collection.
- Demo reset refuses service-install production data paths before creating
  or overwriting files, including nested directories.
- The shutdown intent dialog is extracted from the main window with
  focused regression tests, keeping its existing choices and behavior.
- Startup loads the saved ATEM address from effective settings before the
  monitor starts, instead of requiring it to be entered again in Settings.
- ATEM polling detects a dropped link instead of continuing to report
  cached program input as a live connection.
- An unavailable data directory no longer aborts data_paths at import time,
  before startup logging and crash handling can be installed.
- Returning to the wizard installation page resumes the active provisioning
  request instead of starting a second one; completed attempts remain retryable.
- Restore rejects malformed manifest structures with a controlled error before
  creating a safety backup or restoring data, including in dry-run mode.
- test_config_validators prefers real PyQt5 modules over leaving stubs in
  sys.modules, which poisoned later real-widget tests in the same process.
- Role elevation overlay now applies the progressive lockout: the lockout
  state is shared between both overlay instances, so failed attempts cannot
  be retried without limit.
- Splash TCP scan no longer flags healthy installs as failed (red TCP chip
  on every startup since 8c8e8a6).
- The config/layout fingerprint no longer aborts with UnicodeDecodeError on
  invalid-encoding files; it reports "invalid" and keeps the identity
  computable.
- cleanup_legacy_rpi_autostart.sh no longer records "Disabled" when the
  disable/mask/quarantine step failed; failures are reported as failures.
- Diagnostics no longer reference a non-existent Status.WARN, which crashed
  `khptz doctor` in user mode when a credential was unreadable.
- An active password lockout now survives Operator/Admin mode toggles:
  the button stays disabled and the timer keeps running until it expires.
- cleanup_legacy_rpi_autostart.sh now passes the bare unit name to
  systemctl (the inherited IFS broke column splitting, so legacy services
  silently survived the migration while the report claimed they were disabled).
- test_seat_builder no longer leaves fake SpecialDragButton/QtSvg stubs in
  sys.modules, which poisoned later real-widget tests in the same process.
- Login mode toggle (Operator/Admin) no longer resets the failed-attempt
  counter, so the progressive lockout cannot be bypassed by switching modes.
- Legacy migration escapes backslashes in values written to config.yaml,
  so migrated values round-trip byte-exact and the generated file stays valid YAML.
- Restore rejects a backup whose manifest declares a hash for a member
  missing from the archive, before any write, in both normal and dry-run mode.
- Support bundle: collector errors and content are redacted before the ZIP is
  written, and a redaction failure produces no export.

## 1.2.0 - 2026-11-10

Supervised Raspberry Pi camera-test release. Physical acceptance is pending;
this release is not pilot-ready until those checks are recorded.

### Fixed

- Camera-addressed VISCA responses, command/response freshness, priority STOP,
  worker retirement, recovery and shutdown races.
- Shared camera configuration hydration and validated runtime endpoint
  persistence without granting write access to protected system configuration.
- Camera discovery and Settings checks no longer disrupt managed sessions.
- Exposure readback after confirmed adjustment, including a final refresh
  after repeated presses.
- A stale session standby cannot power off a replacement session's cameras.
- Wizard camera role ordering and exact camera details on the review page.
- A completed pan STOP is no longer resent, and a second STOP no longer closes
  the session. Pan and zoom STOP frames are delivered as one atomic batch, and a
  STOP with a stopped bus no longer leaves motion requests blocked.
- Camera workers are created only for registered, non-empty IPs, are rejected
  after a terminal stop-all, and Exit and power off sends standby before the
  worker is retired. Startup and zoom/AE skip cameras with an empty IP.
- Repeating the same camera IP after a failed runtime repoint retries it.
- QMessageBox buttons are sized to show their full text.

### Changed

- Touch-sized vertical scrollbars and setup password visibility controls.
- The start-up "Turn on the cameras now?" prompt is touch-sized and does not block
  the interface.
- Runtime endpoint overrides are included in backup/restore. An application-only
  downgrade to 1.1.0 does not apply these overrides; preserve configuration and
  runtime data together before updating.

## 1.1.0 - 2026-11-10

First supervised-installation candidate. Automatic tests and container
installer rehearsals do not validate Pi/ARM hardware, the touch screen, real
systemd or physical cameras: this release is `not pilot-ready` until the
supervised install records its results in `docs/MVP_VALIDATION_REPORT.md`.

### Added

- **Provisioning, admin secret storage and restore hardening (PR #16).**
  Production `admin.enc` moves out of the shared data directory into
  `/etc/khptz/secrets` (parent `root:khptz` 0750); missing, corrupt or
  unreadable administrator credentials deny access with no implicit fallback
  to the operator password; root-side cleanup no longer follows symlinks or
  FIFOs and temporary writes use unique `O_EXCL` files; the wizard rollback
  tracks the protected admin store; the acceptance validator checks
  `admin.enc` at its protected path.
- **Supervised installation documentation (PR #128).** `docs/INSTALL_TODAY_ES.md`
  checklist pins the exact reviewed commit for the supervised install;
  `docs/INSTALL_RPI_ES.md` aligns the Spanish guide with the post-hardening
  state.


- **VISCA robustness: bounded command retries, no-response watchdog and a visible reconnecting state.**
  Fire-and-forget camera commands (moves, zoom drives, preset recalls) are
  retried with short, interruptible back-offs (`CAMERA_COMMAND_RETRY_POLICY`,
  1 s and 3 s) instead of being dropped after a single failed attempt. STOP
  commands keep their immediate priority path — a pending STOP aborts any
  retry wait within 0.2 s (the wait polls for it every 200 ms) — and confirmed commands still never execute after their
  deadline. After several consecutive commands with no VISCA response frame,
  the worker flags the camera in `ERROR` state (visible on the LED and in the
  log) while the heartbeat keeps reconnecting; the camera button LED now shows
  amber while a (re)connection attempt is in progress; and the supervisor
  restarts a worker thread that shows no signs of life for 30 s instead of
  only checking that the thread is technically alive. The stuck thread is
  signalled to stop and only replaced once it has actually exited, so two
  workers never share one camera session; if it does not stop within a
  bounded wait, no new thread is started and the camera is flagged
  `ERROR` instead. Failure callbacks now fire exactly once per failed
  command (a command expiring during a retry back-off could previously
  notify failure twice).

### Fixed

- **Product rollback could never run.** `install.sh` deploys `/opt/khptz` with
  `rsync --exclude='.git'` and leaves it `root:khptz` 0750, so `rollback.sh`'s
  preflight check for a git repository in the install directory always failed —
  and past it, `git checkout` and the `PREVIOUS_VERSION` write targeted a tree
  the service user cannot write. Rollback is now a re-deploy: `install.sh`
  records the source checkout, the live ref and the ref it replaced in
  `/etc/khptz/install-state.env`, and `rollback.sh` checks that checkout out at
  the previous ref and re-runs `install.sh` (preserving `--wizard-user`).
  Customer config, both password secrets and the `.provisioned` marker live
  outside the deploy target, so a rollback does not re-run the setup wizard or
  re-prompt for passwords.
- **Product installs invoked `pip3` without requiring it.** The guard tested
  `requirements-rpi.txt` for non-zero size, which is true for a comment-only
  file, so the branch always ran. `pip3` is not a product-mode prerequisite, so
  under `set -e` the install aborted after the service user and directories
  existed but before the application was copied. The installer now checks for a
  real requirement line and requires `pip3` only when there is one.
- **The setup wizard could not configure a second camera.** The installer seeds
  the one-camera starter template and the wizard pre-fills from it, but the
  Cameras page rendered only what it was given and offered no way to add more —
  so a two-camera room (`platform` for the first seats, `comments` for the rest)
  was unreachable through first-run setup or repair, and `/etc/khptz` is not
  editable from the desktop session either. The page now supports Add camera and
  per-camera Remove; the rule for an added camera's role, id, VISCA address and
  IP lives in `application/provisioning_service.next_camera_answer` so it stays
  testable without a screen and cannot produce a value the config loader rejects.
- Rollback no longer aborts when `install-state.env` is absent (`pipefail`
  propagated `sed`'s exit status out of a command substitution), and a git ref
  containing `/` no longer produces an unusable pre-rollback backup path.
- Re-running `install.sh` on the ref that is already deployed (permission repair,
  re-registering units) now carries the existing rollback target forward instead
  of blanking it, which had silently disabled rollback.

### Changed

- Product deploys use `rsync --delete`, so `/opt/khptz` is an exact mirror of the
  installed release and a downgrade cannot leave newer files behind. A developer
  checkout cloned directly into the install directory is no longer rsynced onto
  itself.
- Documentation updated for the deploy-artifact model and the on-device setup
  flow: `README.md`, `docs/INSTALL_RPI.md` (new first-run setup section),
  `docs/UPDATE_ROLLBACK.md`, `docs/RUNTIME_PATH_CONTRACT.md`,
  `docs/RELEASE_CHECKLIST.md`, `docs/KNOWN_LIMITATIONS.md`. Corrected a stale
  README claim that a `config_dialog.py` architecture exception remained — the
  temporary-import exception budget is 0/0.

## 3.38.3

### Changed

- Unified UTC timestamp generation into a single `domain/time_utils.py` helper
  (`utc_now_iso`, `utc_now_compact`), replacing five duplicated `_utc_now()`
  definitions and two inline copies. Fixed a format inconsistency where
  incident snapshots and support bundles used second precision while events,
  audit log and session records used millisecond precision — all structured
  records now share the canonical millisecond ISO-8601 format for reliable
  correlation in support investigations.
- Converted 34 `logger.error(..., exc)` calls inside `except` blocks to
  `logger.exception(...)` so full tracebacks are captured in logs and support
  bundles (camera/ATEM adapters, layout, backup, safety/reset, runtime services,
  bootstrap, config and UI error paths).

### Fixed

- Annotated missing explicit `Optional` type hints (6) and `ClassVar`
  declarations for class-level mutable attributes (9) to remove ambiguous
  implicit-`None` defaults and shared-mutable-default warnings.

## 3.38.2

### Fixed

- Fixed runtime path and demo profile regressions.

## 3.38.x

### Added

- Added Architecture Decisions Record (`docs/ARCHITECTURE_DECISIONS.md`) — formal ADR entries for UI/hardware boundary, `ApplicationController`, `SessionService`, `CameraPort`, `AsyncEventBus` policy, data writes, `CommandResult` and startup idempotency (#692).
- Added application lifecycle startup and shutdown contract (`docs/LIFECYCLE_CONTRACT.md`) — startup order, shutdown order, ownership table, failure states and invariants (#691).
- Added `OperationResult` contract and `OperationCode` taxonomy in `domain/supportability.py` — application-level result wrapper with severity and message (#733).
- Added command vs event policy (`docs/COMMAND_EVENT_POLICY.md`) — workflow table and antipatterns for `ApplicationController` commands vs `AsyncEventBus` events (#690).
- Added state ownership audit (`docs/STATE_OWNERSHIP_AUDIT.md`) — where each piece of state lives, runtime source of truth and duplication risks (#736).

### Changed

- Routed focus, AE, backlight and zoom through `CameraPort`; removed direct VISCA calls from UI (#747).
- Wired `Controller` through `CameraPort` (`ViscaCameraAdapter`) — primary camera-command path no longer goes through legacy `ViscaController` in the controller layer (#744).
- Seat buttons now rendered from `LayoutService` (`room_layout.json`) with `SEAT_POSITIONS` fallback (#743).
- Camera IPs now injected from `config.yaml` into `CameraService`; legacy `.txt` files deprecated (#737).
- Removed unused `SeatAdapter` — seat input routes exclusively through `ApplicationController` (#735).
- Removed `ViscaController` legacy adapter (#746).

### Fixed

- Fixed invalid GitHub Actions versions (`checkout@v4`, `setup-python@v5`) (#748).

## 3.36.x–3.37.x

### Added

- Added `CameraPort` protocol (`ports/camera_port.py`), `FakeCameraPort` and `ViscaCameraAdapter` (`adapters/visca_camera_adapter.py`) (#686).
- Added `ApplicationController` as the single public UI-to-application command boundary (`core/`) (#682).
- Added `CameraConnectionState` enum, `connection_state_changed` signal and standardised silent exception handlers (#96, #97, #100, #725).
- Added demo ATEM control panel for manual fake-ATEM interaction in demo mode (#298).
- Added ATEM automation state snapshot and full safety-mode tests (#178).
- Added preset test runner MVP in Settings → Test tab with seat highlights (#703, #710, #711, #712).
- Added preset brightness persistence module included in backup (#680).
- Added named-seats mode and tri-state PTZ indicators for preset test runner (#710, #711).
- Added architecture audit report (`docs/ARCHITECTURE_AUDIT_REPORT.md`) (#707).
- Added comprehensive test coverage — 8 new test files; backlog pruned to 9 xfails.
- Added GPIO monitor tests — last untested source module (#745).

### Changed

- Routed cancel_polls through `SessionService`; removed direct `_visca` call from session path (#684).
- Removed direct VISCA call from `config_dialog` preset test; one documented exception remains under #686 (#683).
- Routed joystick, presets and ATEM actions through `AsyncEventBus` (#204, #40, #207).
- Routed session lifecycle and home through `AsyncEventBus` (#215).
- Updated all import paths after Phase 2c/2d module moves (modules now live under `ui/`, `adapters/`, `runtime/`).

### Fixed

- Fixed ATEM home button, ON AIR indicator and auto-home via `EventBus`; preset test runner wiring.
- Fixed destroyed-signal crash in preset test runner.
- Fixed session shutdown tests to verify `EventBus` events.

## 3.34.x–3.35.x

### Added

- Added role/permission model; `camera_operator` is the default access role (#718, #719).
- Added unique command IDs to VISCA log entries (#160).
- Added test to prevent secrets appearing in log calls (#89).
- Added repo hygiene GitHub Actions workflow (#55).
- Added password-not-configured warning on login screen (#88).
- Added bounded retry policy for camera and ATEM connections (#96).
- Added startup summary logging; converted `FlightRecorder` to use the logger (#16).
- Added installation ID generation on first install; starter profile regression tests (#663, #679).
- Added `--check` mode, static tests and `verify-install` command for the installer (#670, #671, #672, #678).
- Added regression tests for `--profile demo` isolation (#659, #677).

### Changed

- Seat call pulse limited to 3 blink cycles (#658).
- Hardened Raspberry Pi installer preflight checks and permission alignment (#669, #674, #675, #676).

### Fixed

- Fixed runtime path/config drift in diagnostics, support bundles and fingerprints (#654).
- Fixed `eval` in `rollback.sh` run() helper — replaced with safe arg passing (#378).
- Fixed import paths after Phase 2c/2d module moves.

## 3.30.x–3.33.x

### Added

- Added camera power-state check at startup and screen-off camera shutdown dialog.
- Added ATEM state reporting; replaced suspicious default fallback IP with explicit unconfigured state.
- Added `sim_mode.py show` command and simulation helper rework.
- Added zoom +/- variable-step buttons by range.
- Added `OperationResult` / `CommandResult` plumbing in `domain/` and `application/` layers.
- Added `AccessModeService`, `DemoGuard`, `DemoResetService` and demo isolation plumbing.
- Added manifest backup and safe restore; backup included in `AppContext` and CLI.
- Added `LayoutService`, `room_layout.json`, schema/recovery, import/export, coordinate scaling.
- Added `FlightRecorder`, `ChangeHistoryService`, `IncidentService`, `EvidenceSnapshotService`.
- Added `DiagnosticsService`, `HealthDiagnostics`, `NetworkDiagnostics`, startup error classification.
- Added `SupportBundleService`, `RedactionService`, `SupportabilityService` foundations.
- Added `SessionService`, `SessionMarker` and session interrupt recovery.
- Added `FingerprintService`, `MaintenanceService`, `WarrantyStateService`.
- Added `PresetService`, `PresetVerificationService`, `PresetTestRunner`.
- Added `CrashReporter` and crash log writing.
- Added `NetworkHandoverReport` and `KnownGoodStateService`.

### Changed

- Moved all UI files to `ui/`; adapters to `adapters/`; runtime code to `runtime/`.
- Completed Phase 2a/2b/2c/2d architecture migration — all imports updated.
- `bootstrap.py` now owns full `AppContext` construction and dependency wiring.

## 3.0.6

### Changed

- Made ATEM monitoring safer when ATEM is not configured, unreachable, or missing its optional dependency.
- Replaced the suspicious default ATEM fallback IP with an explicit unconfigured state.
- Added explicit ATEM state reporting for UI/status handling.

## 3.0.5

### Added

- Added `NOTICE.md` with proprietary/confidential project notice.
- Added `.github/pull_request_template.md` for safer pull request review.
- Added `docs/KNOWN_LIMITATIONS.md` and linked it from the README.

### Changed

- Refreshed README limitations to point to the maintained known-limitations document.

## 3.0.4

### Added

- Added `THIRD_PARTY_NOTICES.md` listing runtime, optional and development dependencies with their licences and a PyQt5 commercial-distribution warning (closes #24).

## 3.0.3

### Changed

- Standardised copyright headers across all 82 Python source files: replaced verbose Spanish-language "uso privado exclusivo" notices with a concise two-line English header (closes #25).

## 3.0.2

### Added

- Added `docs/LEGAL_CHECKLIST.md` for pre-customer deployment legal review (closes #26).

## 3.0.1

### Added

- Added `requirements.txt`, `requirements-dev.txt` and `requirements-rpi.txt`.
- Added `requirements-atem.txt` for optional Blackmagic ATEM monitoring dependencies.
- Added README documentation aligned with the current implementation.
- Added Raspberry Pi dependency guidance.
- Added this changelog.
- Added `VERSION` file.
- Added example configuration files under `config.example/`.
- Added pytest configuration.
- Added GitHub Actions test workflow.

### Changed

- Kept `requirements.txt` focused on core runtime dependencies.
- Removed optional ATEM dependency from default runtime/dev install path so CI and tests do not depend on `PyATEMMax`.
- Kept `requirements-rpi.txt` minimal; install `requirements-atem.txt` separately only on systems using a real ATEM.

### Notes

- The current implementation is still hybrid: new `core/`, `application/` and `domain/` layers exist, but legacy Qt controllers are still used by `main_window.py`.
- Login fallback behaviour still needs hardening before wider customer deployment.
- Audit logging code exists but is currently disabled in normal login flow.

## 3.0.0

### Current baseline

- Two-camera VISCA-over-IP PTZ control.
- Touchscreen-oriented PyQt5 interface.
- Seat preset recall and speaker assignment.
- Chairman personal preset allocation.
- Optional ATEM monitoring.
- Simulation mode for VISCA cameras.
- Persistent data directory under `~/.config/khptz/` by default.
