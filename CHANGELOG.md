# Changelog

All notable changes to this project should be documented in this file.

This project uses a simple versioning approach while it is still in early product development:

- Patch version: documentation, tests, install scripts, small fixes.
- Minor version: new features or significant refactors.
- Major version: breaking changes for installation, configuration or customer deployments.

## Unreleased

### Fixed

- **Product rollback could never run.** `install.sh` deploys `/opt/hallptz` with
  `rsync --exclude='.git'` and leaves it `root:hallptz` 0750, so `rollback.sh`'s
  preflight check for a git repository in the install directory always failed —
  and past it, `git checkout` and the `PREVIOUS_VERSION` write targeted a tree
  the service user cannot write. Rollback is now a re-deploy: `install.sh`
  records the source checkout, the live ref and the ref it replaced in
  `/etc/hallptz/install-state.env`, and `rollback.sh` checks that checkout out at
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
  was unreachable through first-run setup or repair, and `/etc/hallptz` is not
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

- Product deploys use `rsync --delete`, so `/opt/hallptz` is an exact mirror of the
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
- Persistent data directory under `~/.config/hallptz/` by default.
