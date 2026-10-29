# Implementation Plan

This document defines the practical execution order for turning Hall PTZ Control into an installable, supportable Raspberry Pi product.

The current release target is:

```text
v0.1.0-installable-mvp
```

Current state:

```text
Installable MVP candidate. Most MVP foundations are merged; release-candidate QA and hardening remain.
```

The rule is simple: stabilise the MVP candidate before starting advanced visual editor, advanced ATEM, online licensing, cloud dashboard or multi-room features.

---

## Scope lanes

| Scope | Meaning |
|---|---|
| MVP foundation | Required for the first installable and supportable deployment candidate. |
| Release-candidate QA | Validation needed before customer use. |
| Post-MVP | Useful soon after MVP, but not required to prove the product can be installed and supported. |
| Future | Valuable later, but not needed for the first customer-ready version. |

---

## Release readiness states

Use these states when describing validation:

```text
demo/no-hardware validated
pre-RC smoke passed
Pi validated
pilot-ready
pilot-ready with limitations
not pilot-ready
```

Rules:

- No real Raspberry Pi validation means `not pilot-ready`.
- No support bundle MVP means `not pilot-ready`.
- Demo/no-hardware validation is useful evidence, but it is not pilot/customer readiness.
- #381 remains the real Raspberry Pi validation gate.
- #520 remains the human pre-RC/release checklist source.
- #27 remains mandatory support bundle MVP work before first pilot readiness.
- #288 remains the MVP scope source and should not become a duplicate checklist.
- Post-MVP/future work must not block pilot readiness unless explicitly promoted into the pilot/customer-required set.

Issue classification should distinguish:

```text
pilot/customer required
post-MVP/future
```

This can be done with labels, checklist sections in #455/#520 or both. Do not relabel the entire backlog blindly; document the policy first and update issue classification in a focused planning pass.

---

## MVP foundation status

The MVP foundation now includes:

- architecture rules, boundary tests and formal Architecture Decisions Record;
- `ApplicationController` as the single UI-to-application command boundary;
- `CameraPort` protocol and `ViscaCameraAdapter` — primary camera-command path wired;
- command vs event policy documented and enforced;
- application lifecycle contract (startup/shutdown order);
- state ownership audit;
- `bootstrap.py` and `AppContext`;
- validated config foundation and YAML defaults;
- camera IPs injected from `config.yaml` (legacy `.txt` deprecated);
- role/permission model (`camera_operator` default);
- `OperationResult`/`OperationCode`/`OperationSeverity` taxonomy;
- seat buttons rendered from `LayoutService`/`room_layout.json` with fallback;
- demo ATEM panel; `FakeCameraPort`; demo profile regression tests;
- preset test runner MVP;
- Starter/Standard/Demo config templates;
- camera registry foundation;
- pytest CI, lint and support workflows (2 500+ tests);
- `hallptz` CLI;
- systemd service template;
- installer script;
- rollback script;
- `hallptz doctor` diagnostics;
- offline/demo/profile foundations;
- installation profile and installation ID foundations;
- local network/IP diagnostics;
- disk/temperature/log health checks;
- legacy `.txt` migration command;
- manifest backup;
- safe restore;
- persistent `room_layout.json` foundation;
- layout schema/recovery;
- layout import/export foundations;
- fake camera and fake ATEM foundations;
- demo reset command.

These are not enough by themselves for unattended customer deployment. They must pass release-candidate QA.

---

## Release-candidate QA block

Do next before selling/installing as customer-ready:

```text
1. Create v0.1.0-rc1 tag or release-candidate branch.
2. Run pytest, architecture tests and ruff.
3. Run release-check workflow/manual checklist.
4. Test fresh Raspberry Pi install.
5. Test systemd service start/restart/reboot.
6. Test hallptz version/status/doctor.
7. Test Starter one-camera profile.
8. Test Standard two-camera profile.
9. Test ATEM disabled and ATEM enabled cases.
10. Test backup and restore on non-customer data.
11. Test rollback from a failed update path.
12. Test demo profile isolation and demo reset.
13. Test session start/end and interrupted-session recovery.
14. Run day-run/soak test with real hardware.
15. Record known limitations and release notes.
16. Confirm #27 support bundle MVP availability before first pilot readiness.
```

Exit criteria:

```text
installable
startable
diagnosable
recoverable
explainable to operator/support
```

---

## Next implementation blocks

### Block A — Documentation/backlog synchronisation

```text
- close/update stale issues that are already implemented
- update roadmap and implementation docs
- align README, installation, configuration, support and release docs
```

Exit criteria:

- Planning status reflects actual state.
- No docs say “planned” for features that now exist.
- Remaining limitations are explicit.
- Pilot/customer-required work is separated from post-MVP/future work.

### Block B — Runtime/customer data separation

```text
- finish separation of app code from customer/runtime data
- move/migrate password.enc to persistent config/data path
- audit root config/customer files
- harden path handling from non-repo CWD
- review Linux permissions for service user/data/logs/backups
- align production direction around `/opt/hallptz`, `/etc/hallptz`, `/var/lib/hallptz` and `/var/log/hallptz`
- use a dedicated `hallptz` user for production Raspberry Pi installs
```

Exit criteria:

- customer data is not stored in source tree by default;
- updates do not overwrite customer data;
- service user can read/write only required paths.

### Block C — Production support hardening

```text
- enable/verify persistent rotating logs
- add sanitized support bundle export
- add secrets-in-logs guardrail
- add command IDs for important VISCA/support logs where useful
- improve config diff/change history diagnostics
- include version, build/git commit where available and active profile/mode in startup logs
- expose support bundle export from CLI and UI when the service is available
```

Exit criteria:

- support can diagnose remotely without guessing;
- support bundle excludes secrets;
- logs are useful and not noisy.

### Block D — Layout/runtime correctness

```text
- finish seat_id / label / preset / camera_role decoupling
- render seat buttons from persistent room_layout.json
- migrate seat_names.json keys safely
- validate protected presets and duplicate preset warnings
- keep visual layout editor as a separate later block
```

Exit criteria:

- renaming/moving a seat does not change its preset;
- seat click routes by camera_role, not currently selected camera;
- existing customer names are not lost.

### Block E — Operator/session reliability

```text
- block unsafe camera movement outside active session
- route session start/end/home fully through SessionService
- reduce direct UI-to-VISCA control paths
- add clear operator feedback for blocked/moving/error states
- keep emergency STOP explicit and high priority
- preserve the CALL/SET contract: short tap/left click CALL, long press/right click SET only in admin/installer contexts
- require explicit confirmation before overwriting real presets
```

Exit criteria:

- operator cannot accidentally move cameras outside allowed state;
- session logic has one source of truth;
- UI remains responsive during camera failures.

### Block F — Architecture boundary cleanup

```text
- use ApplicationController as the public UI command API
- use AsyncEventBus for events, notifications, diagnostics, logging and integrations
- introduce CameraPort
- ✓ socket/VISCA details moved to ViscaCameraAdapter (CameraService removed in 3.38.x)
- reduce global CAM1/CAM2 dependency in application layer
- continue migrating UI actions through controller/services
- remove temporary architecture test exceptions when safe
```

Exit criteria:

- application layer describes intent;
- adapters handle hardware/protocol details;
- UI no longer owns camera command logic.

### Block G — Commercial controls

```text
- offline signed license model
- LicensingService
- hallptz license status
- plan name, expiry, max cameras and feature flags
- tests for valid/expired/tampered licenses
```

Exit criteria:

- offline license validation works;
- plan limits can be reported/enforced clearly;
- private signing key is never committed.

---

## Post-MVP Startup Gate direction

The existing splash/status direction should be unified as `Startup Gate`, a readiness gate before normal operation.

Main states:

```text
Ready
Warning
Blocked
```

Direction:

- invalid `config.yaml` blocks normal operation and offers repair/recovery guidance;
- required-camera failures can show `Find missing camera` and targeted diagnostics;
- `Run doctor` is shown when useful, not in the clean Ready path by default;
- `Export support bundle` is shown only when the support bundle service is available;
- demo mode uses unmistakable wording such as `DEMO MODE - NO REAL HARDWARE COMMANDS`;
- installer/admin contexts may show pilot readiness as ready, ready with limitations or not ready;
- last successful startup, last backup and last config change are shown where available;
- Startup Gate calls diagnostics/readiness/support services instead of duplicating probing, support bundle, backup/restore or licensing logic.

This is post-MVP / first-pilot polish. It should not block the first MVP release unless #381/#520 validation shows startup confusion, unsafe demo/startup behaviour or config recovery gaps are preventing pilot/customer use.

---

## Not in current MVP release candidate

- full visual layout editor;
- Startup Gate implementation;
- full seat properties panel;
- layout generator/templates;
- multi-room profiles;
- polished guided demo playback;
- advanced ATEM control;
- online license validation;
- cloud dashboard;
- web UI.

---

## Dependency notes

| Work | Depends on |
|---|---|
| Runtime data separation | path ownership, backup/restore, installer paths |
| Support bundle | persistent logs, diagnostics, backup/sanitisation rules |
| Seat decoupling | LayoutService, room_layout schema, migration tests |
| Visual layout editor | seat decoupling, validation, backup/import/export, admin protection |
| Session unification | SessionService, camera command routing, UI/controller boundaries |
| CameraPort adapter boundary | ✓ complete — ViscaCameraAdapter implements CameraPort; one exception remains in config_dialog.py (#686) |
| Licensing | installation ID, profile, config loader, camera registry |
| ATEM automation | ATEM service boundary, safety modes, fake ATEM tests |

---

## Execution rule

Do not start a later block if it depends on unfinished foundation work.

If a task does not help installation, support, configuration, testing, operator reliability or commercial licensing, it waits.
