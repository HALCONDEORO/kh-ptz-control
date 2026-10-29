# Roadmap

This is the concise roadmap for KH PTZ Control.

The practical execution order is in `docs/IMPLEMENTATION_PLAN.md`.

---

## Current release target

```text
v0.1.0-installable-mvp
```

Goal: first Raspberry Pi version that can be installed, diagnosed, backed up, restored and configured for a basic customer room.

Current state:

```text
Installable MVP candidate.
Core assets exist; Raspberry Pi QA/release-candidate validation remains.
No build is pilot-ready without real Raspberry Pi validation and support bundle MVP availability.
```

---

## Delivery phases

| Phase | Delivery block | Main goal | Current state |
|---:|---|---|---|
| 1 | Foundation | Safe architecture, config and tests. | Complete — `ApplicationController`, `CameraPort`, boundary tests all merged. |
| 2 | Installable runtime | CLI, systemd, installer and diagnostics. | Assets exist; needs Raspberry Pi QA. |
| 3 | Site readiness | Installation identity, profile, offline mode and health checks. | Foundations exist; installation ID generation merged; needs profile validation on Pi. |
| 4 | Customer data safety | Backup, restore, migration and change visibility. | Backup/restore merged; support bundle/config diff still pending. |
| 5 | Room installation workflow | Persistent layout and safe room configuration. | Seat buttons now render from `room_layout.json`; visual editor and full seat decoupling pending. |
| 6 | Operator reliability | Clear and predictable live operation. | `ApplicationController` boundary enforced; session state consolidation and safe command blocking pending. |
| 7 | Demo and integrations | Safe demo mode and defined ATEM behaviour. | Demo ATEM panel merged; full demo UI polish and ATEM safety controls pending. |
| 8 | Commercial controls | ~~Offline license and plan enforcement.~~ | **Dropped 2026-09-11**: the project is MIT-licensed (owner decision); paid/offline licensing no longer applies. |
| 9 | Hardening / future | Dependency audit, docs checks, templates, multi-room and online features. | Some workflows exist; future features pending. |

---

## MVP: implemented / merged foundation

The following MVP foundations are now present in the repository:

- architecture rules and boundary tests;
- `bootstrap.py` and `AppContext`;
- typed config/default profile direction;
- Starter/Standard/Demo config templates;
- camera registry foundation;
- pytest CI;
- Ruff lint workflow/config;
- shellcheck workflow;
- dependency audit workflow;
- `khptz` CLI foundation;
- `khptz version`, `khptz status`, `khptz doctor`;
- `khptz migrate`;
- `khptz backup`;
- `khptz restore`;
- systemd service template;
- installer script;
- rollback script;
- offline/demo/profile foundations;
- installation ID/profile foundations;
- local network/IP diagnostics;
- disk/temperature health checks;
- manifest backup;
- safe restore;
- persistent `room_layout.json` foundation;
- `LayoutService`;
- layout schema/recovery;
- layout import/export foundations;
- fake camera and fake ATEM foundations;
- demo reset command.

---

## MVP: still needs QA before customer deployment

Before calling the MVP customer-ready:

- create a release candidate tag;
- run full test/lint/release checks;
- test fresh install on target Raspberry Pi image;
- test systemd boot/start/restart;
- test `khptz doctor` on Raspberry Pi;
- test real camera startup and session start/end;
- test one-camera Starter and two-camera Standard profiles;
- test ATEM disabled and ATEM enabled cases;
- test backup and restore on non-customer data;
- test rollback from a failed update;
- test demo isolation;
- confirm #27 support bundle MVP availability;
- run a day-run/soak test;
- update release notes and known limitations.

Use these readiness terms consistently:

```text
demo/no-hardware validated
pre-RC smoke passed
Pi validated
pilot-ready
pilot-ready with limitations
not pilot-ready
```

Demo/no-hardware validation must not be presented as pilot/customer readiness. Post-MVP/future issues must not block pilot readiness unless explicitly promoted into the pilot/customer-required set.

---

## Post-MVP near-term work

Next high-value work after release-candidate stabilisation:

1. Prepare `v0.1.0-installable-mvp` release candidate tag.
2. Complete customer/runtime data separation — retire legacy `.txt` config files.
3. Enable/verify persistent rotating production logs.
4. Add sanitized support bundle export (#27).
5. Finish `seat_id`, `label`, `preset`, `camera_role` decoupling across runtime paths.
6. Consolidate session state: wire `SessionService` to update `SystemState.session`.
7. Complete `config_dialog.py` boundary cleanup — remove remaining direct VISCA import (#686).
8. Block unsafe camera commands outside active session.
9. Add offline signed license validation foundation.

Startup Gate is a post-MVP UX direction that unifies splash/status/readiness concepts into Ready, Warning and Blocked states. It should not block the first MVP release by default, but it can be promoted if #381/#520 validation shows startup confusion or config recovery gaps.

---

## Future

Future items include:

- full visual layout editor;
- seat properties panel;
- layout generator/templates;
- guided seat preset calibration;
- preset verification workflow;
- multi-room profiles;
- advanced ATEM control;
- online license validation;
- cloud dashboard;
- remote management.

---

## Key documents

| Document | Purpose |
|---|---|
| `docs/IMPLEMENTATION_PLAN.md` | Practical work order and dependency matrix. |
| `docs/DEFINITION_OF_DONE.md` | Completion rules for issues and PRs. |
| `docs/DECISIONS.md` | Product and technical decisions. |
| `docs/FIRST_CUSTOMER_CHECKLIST.md` | First installation/handover checklist. |
| `docs/RELEASE_CHECKLIST.md` | Release-candidate/customer deployment checklist. |
| `docs/KNOWN_LIMITATIONS.md` | Current unresolved limitations. |

---

## Rule

Stabilise the installable MVP candidate before starting advanced editor, licensing, cloud, online validation or multi-room work.
