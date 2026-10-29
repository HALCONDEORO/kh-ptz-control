# Documentation Index

This index explains which document to use depending on the task.

Current repository state:

```text
Working application + installable MVP candidate.
Use release/checklist docs before customer deployment.
Do not treat the MVP as customer-ready until #381 and docs/MVP_VALIDATION_REPORT.md are completed.
```

---

## For current state overview

| Document | Use it for |
|---|---|
| [`README.md`](../README.md) | High-level project status, quick start, scope, limitations and next work. |
| [Known limitations](KNOWN_LIMITATIONS.md) | Current technical/product limitations and customer-readiness risks. |
| [Roadmap](ROADMAP.md) | MVP state, release-candidate QA and next product phases. |
| [Startup Gate UX direction](STARTUP_GATE.md) | Post-MVP startup/readiness gate states, actions and ownership boundaries. |

---

## For MVP/release validation

| Document / issue | Use it for |
|---|---|
| [Release checklist](RELEASE_CHECKLIST.md) | Safe release/update checklist before release candidate or customer update. |
| [Release readiness checklist](RELEASE_READINESS_CHECKLIST.md) | Human-readable gate for calling a build demo-ready or customer-ready (feeds automated gate #452). |
| [MVP validation report](MVP_VALIDATION_REPORT.md) | Recorded Raspberry Pi validation evidence and PASS/FAIL/PASS WITH LIMITATIONS decision. |
| Raspberry Pi MVP validation gate | Real-hardware validation checklist; evidence is recorded in `docs/MVP_VALIDATION_REPORT.md`. |

---

## For project planning

| Document | Use it for |
|---|---|
| [MVP dependency map](MVP_DEPENDENCY_MAP.md) | Remaining open issue groups, dependencies and recommended next-PR execution order. |
| [Implementation plan](IMPLEMENTATION_PLAN.md) | Release-candidate QA, next implementation blocks and dependency notes. |
| [Technical decisions](DECISIONS.md) | Product and architecture decisions that should not be repeatedly debated. |
| [Startup Gate UX direction](STARTUP_GATE.md) | Unified splash/status/readiness UX direction for post-MVP work. |
| [ATEM manual integration plan](ATEM_MANUAL_INTEGRATION_PLAN.md) | Phase 1 manual ATEM scope, safety policy, architecture boundary, validation gate and future issue split. |
| [ATEM dependency decision](ATEM_DEPENDENCY_DECISION.md) | Evaluated options, chosen library (PyATEMMax MIT), version/range, fallback path and revalidation policy. |
| [ATEM auto-preview future design](ATEM_AUTOMATION_FUTURE.md) | Design-only architecture for a future opt-in ATEM auto-preview feature (Phase 2+); no automation enabled. |
| [Definition of Ready](DEFINITION_OF_READY.md) | Readiness rules before implementation starts. |
| [Definition of Done](DEFINITION_OF_DONE.md) | Completion rules for issues and pull requests. |
| [Architecture](ARCHITECTURE.md) | Layer rules, forbidden imports and legacy exceptions. |
| [Release process](RELEASE_PROCESS.md) | Tagging, release notes, validation evidence and rollback requirements. |
| [Branch protection policy](BRANCH_PROTECTION_POLICY.md) | Required GitHub rules, checks, review policy and emergency hotfix handling for `main`. |
| [Dependency pinning policy](DEPENDENCY_PINNING_POLICY.md) | Dependency ranges, release lock strategy, Dependabot interaction and Raspberry Pi install expectations. |

---

## For commercial planning

| Document | Use it for |
|---|---|
| [Third-party assets](THIRD_PARTY_ASSETS.md) | Provenance and licensing of bundled third-party assets (icons, etc.). |

---

## For developers

| Document | Use it for |
|---|---|
| [Architecture](ARCHITECTURE.md) | Layer rules, forbidden imports and temporary legacy exceptions. |
| [Architecture Decisions Record](ARCHITECTURE_DECISIONS.md) | ADR entries: UI/hardware boundary, ApplicationController, SessionService, CameraPort, EventBus, data writes, CommandResult and startup idempotency. |
| [Command/event policy](COMMAND_EVENT_POLICY.md) | Command vs event policy: workflow table, antipatterns and migration status. |
| [Lifecycle contract](LIFECYCLE_CONTRACT.md) | Startup order, shutdown order, ownership table, failure states and lifecycle invariants. |
| [Concurrency and threading policy](CONCURRENCY_POLICY.md) | Threading model, runtime-state single-source-of-truth rules and safe-access patterns. |
| [Runtime path contract](RUNTIME_PATH_CONTRACT.md) | Canonical paths, ownership, permissions and legacy migration contract for Raspberry Pi service installs. |
| [Seat model contract](SEAT_MODEL_CONTRACT.md) | Seat model fields, CameraTargetResolver API, routing boundaries and legacy migration rules. |
| [CALL/SET interaction contract](CALL_SET_CONTRACT.md) | Unified CALL/SET behaviour across all modes, input events and hardware states. Release-blocking. |
| [Config schema reference](CONFIG_SCHEMA.md) | Canonical field-level schema, validation errors, legacy migration mapping and loader API. |
| [Config policy](CONFIG_POLICY.md) | What configuration is committed vs customer/site-local, and why. |
| [Configuration guide](CONFIGURATION_GUIDE.md) | YAML profiles, legacy migration, runtime data and validation rules. |
| [Black box event schema](BLACK_BOX_SCHEMA.md) | Flight-recorder event schema, retention and redaction policy. |
| [Release checklist](RELEASE_CHECKLIST.md) | Required checks before release candidate or customer update. |
| [Security notes](SECURITY_NOTES.md) | Security guidance for development, deployment and support. |
| [Security incident response](SECURITY_INCIDENT_RESPONSE.md) | Practical response checklist for leaked secrets, compromised SSH, stolen Raspberry Pi and sensitive support data. |
| [Privacy notes](PRIVACY_NOTES.md) | Data and privacy considerations. |
| [Incident classification](INCIDENT_CLASSIFICATION.md) | Support taxonomy, severity, impact, closeout fields and product feedback loop. |

---

## For installers and support

| Document | Use it for |
|---|---|
| [Backup/restore contract](BACKUP_RESTORE_CONTRACT.md) | Backup ZIP structure, manifest schema, restore dry-run, allowed paths and safety rules. |
| [Support bundle contract](SUPPORT_BUNDLE_CONTRACT.md) | Support bundle structure, redaction rules, allowed/forbidden categories and transmission policy. |
| [Raspberry Pi runtime baseline](RPI_RUNTIME_BASELINE.md) | Supported hardware, OS, Python, dependencies and first-pilot validation target. |
| [Raspberry Pi golden image](RPI_GOLDEN_IMAGE.md) | Step-by-step golden-image preparation and provisioning checklist for a new Pi. |
| [Raspberry Pi installation guide](INSTALL_RPI.md) | Single end-to-end install guide: prerequisites, installer, systemd, backup/restore, rollback, validation, troubleshooting, manual fallback and handover. |
| [On-device setup wizard](SETUP_WIZARD.md) | Touchscreen first-run wizard: `khptz setup`, first-boot autostart, Repair mode, privileged provisioning channel and rollback safety. |
| [Network architecture](NETWORK_ARCHITECTURE.md) | Recommended AV VLAN/network design for customer installations (referenced by network diagnostics). |
| [Update and rollback procedure](UPDATE_ROLLBACK.md) | Safe update and rollback steps on a customer Raspberry Pi. |
| [Soak test checklist](SOAK_TEST.md) | Real-world day-run soak test before first paid deployment and major releases. |
| [ATEM installation and handover](ATEM_INSTALLATION.md) | ATEM install, troubleshooting and handover (Phase 1 read-only/manual switching). |
| [ATEM validation report](ATEM_VALIDATION_REPORT.md) | Template — complete one copy per ATEM installation or revalidation event. |
| [Raspberry Pi security baseline](RPI_SECURITY_BASELINE.md) | Optional local firewall, SSH and recovery baseline for appliance/customer mode. |
| [AV device hardening checklist](AV_DEVICE_HARDENING_CHECKLIST.md) | Camera, ATEM, switch and router hardening checklist for installers. |
| [PTZ camera compatibility matrix](PTZ_CAMERA_COMPATIBILITY.md) | Which VISCA-over-IP camera models are validated, hardware validation checklist and observed response patterns. |
| [Release checklist](RELEASE_CHECKLIST.md) | Safe release, update and handover checklist. |
| [MVP validation report](MVP_VALIDATION_REPORT.md) | Final validation evidence before first pilot/customer readiness. |

---

## For operators

| Document | Use it for |
|---|---|
| [Operator guide](OPERATOR_GUIDE.md) | Short guide for normal live operation. |

---

## Runtime entry points

| File | Use it for |
|---|---|
| [`runtime/cli.py`](../runtime/cli.py) | `khptz` command-line entry point. |
| [`domain/supportability.py`](../domain/supportability.py) | `OperationResult`, `OperationCode`, `OperationSeverity` — application-level result contract. `CommandResult` — hardware-level result; convert via `OperationResult.from_command_result()`. |
| [`runtime/systemd/khptz-control.service`](../runtime/systemd/khptz-control.service) | systemd service template. |
| [`runtime/installer/install.sh`](../runtime/installer/install.sh) | installer script. |
| [`runtime/installer/rollback.sh`](../runtime/installer/rollback.sh) | rollback script. |

---

## Repository templates

| File | Use it for |
|---|---|
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | Development workflow and contribution rules. |
| [Pull request template](../.github/pull_request_template.md) | Pull request review checklist. |
| [Bug report template](../.github/ISSUE_TEMPLATE/bug_report.md) | Reproducible bug reports. |
| [Technical task template](../.github/ISSUE_TEMPLATE/technical_task.md) | Focused technical task proposals. |

---

## Rule

Use the smallest document that answers the question. Avoid duplicating the same rule in multiple documents unless it is operationally necessary.

If a document says a feature is planned while the README says it exists, update the document before relying on it for customer work.

If a document says the MVP is ready but #381 or `docs/MVP_VALIDATION_REPORT.md` has not recorded PASS or PASS WITH LIMITATIONS, the document is wrong.
