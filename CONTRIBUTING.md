# Contributing Guide

This repository uses a simple professional workflow to keep the project installable while it is being turned into a product.

---

## Main rule

`main` must remain stable.

Do not mix large changes, refactors, documentation and fixes in the same commit if they can be separated.

Customer installs should use tagged releases or approved release-candidate branches, not random commits from `main`.

---

## Branches

```text
main        = stable / potentially deployable
feature/*   = focused new functionality
fix/*       = focused fix
chore/*     = tooling, documentation, maintenance
refactor/*  = refactor with no expected functional change
docs/*      = documentation-only changes
release/*   = release-candidate preparation
```

Avoid direct pushes to `main` when possible.

---

## Recommended workflow

1. Pick an issue or focused task.
2. Confirm it satisfies the Definition of Ready.
3. Create a focused branch.
4. Make small changes.
5. Run local checks.
6. Open a Pull Request.
7. Review CI, risks and checklist.
8. Merge only when it satisfies the Definition of Done.

---

## Definition of Ready

Before implementation starts, every issue should follow:

```text
docs/DEFINITION_OF_READY.md
```

Required issue fields:

- Parent
- Depends on
- Blocks / Related
- Acceptance criteria
- Status / risk / type
- Tests expected

Use `None` or `not applicable` only when that is intentional and visible.

---

## Local checks

Before opening a PR:

```bash
python3 -m pytest
python3 -m ruff check .
```

Optional pre-commit hooks are available for fast local hygiene checks:

```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

The hooks run formatting hygiene, YAML/JSON checks, Ruff, private-key detection
and a repository hygiene guard for new local runtime/customer artifacts. Full CI
remains the source of truth before merge.

For architecture:

```bash
python3 -m pytest tests/test_architecture_boundaries.py
```

For runtime/config/diagnostics/support changes:

```bash
python3 -m runtime.cli version
python3 -m runtime.cli status
python3 -m runtime.cli doctor
```

For demo/simulation changes:

```bash
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
python3 -m runtime.cli --profile demo demo reset
python3 sim_mode.py show
```

If the change touches UI, cameras, config, startup, installer, systemd, backup/restore, session flow or simulation, test manually when practical.

---

## Demo and simulation

Preferred demo-profile checks:

```bash
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
python3 -m runtime.cli --profile demo demo reset
```

Legacy simulation helper still exists:

```bash
python3 sim_mode.py on
python3 main.py
python3 sim_mode.py off
python3 sim_mode.py show
```

Important: legacy simulation mode can touch legacy IP files. Confirm it is disabled before validating production behaviour.

---

## Definition of Done

Every PR should follow:

```text
docs/DEFINITION_OF_DONE.md
```

Important rules:

- tests added or clear justification;
- `python3 -m pytest` passes;
- `python3 -m ruff check .` passes or the reason is documented;
- normal startup is not broken;
- demo/simulation is not broken if touched;
- `hallptz` CLI impact is considered if runtime/config/diagnostics changed;
- documentation updated if usage/installation/configuration changed;
- no secrets, private keys or customer-sensitive data are committed;
- no new business logic is added to legacy PyQt controllers unless explicitly accepted;
- data migration/recovery considered if applicable;
- backup/rollback safety considered if installer/restore/data paths changed.

---

## Architecture

Before moving logic or adding services, review:

```text
docs/ARCHITECTURE.md
```

Practical rule:

```text
UI requests behaviour.
Application decides behaviour.
Adapters talk to hardware/storage.
Domain knows nothing about PyQt, network or filesystem.
```

Do not add new business logic to `main_window.py` if it can be moved to a service.

Current architecture boundary (as implemented):

```text
ApplicationController is the single UI command boundary.
CameraPort (ports/camera_port.py) is the application-level camera interface.
ViscaCameraAdapter owns socket/VISCA details — migration is complete (3.38.x).
Legacy direct UI-to-VISCA paths are temporary debt, not a pattern to copy.
One documented exception remains in config_dialog.py (#686).
```

---

## Release-sensitive changes

Review `docs/RELEASE_CHECKLIST.md` before merging changes in:

```text
installer
systemd
runtime CLI
backup/restore
config migration
license/security
VISCA/camera movement
session start/end
customer data paths
demo/production isolation
```

These changes need a clear test note and, where applicable, a rollback/data-safety note.

---

## Commits

Use clear messages. Commit messages in this project may be in English or Spanish, but should be specific.

Good examples:

```text
docs: update release checklist for MVP candidate
fix: prevent restore from overwriting active config without backup
refactor: route session end through SessionService
```

Avoid:

```text
fix
changes
update stuff
```

---

## Pull Requests

A PR should include:

- what changed;
- why it changed;
- related issue if applicable;
- how it was tested;
- risks;
- data/backup/rollback impact if relevant;
- Definition of Done checklist;
- screenshots if UI changed.

Use the PR template.

---

## AI / Claude / Codex

AI tools can be used, but changes must be reviewed like normal code.

Rules:

- give AI tools one focused task at a time;
- avoid prompts that mix too many areas;
- allow GitHub auto-merge only after required checks pass and a human review approves it;
- do not give AI private keys, secrets, real customer data or sensitive information;
- review especially carefully changes in installer, backup/restore, VISCA, licensing, configuration and customer data paths.

---

## High-risk areas

Review more carefully:

```text
VISCA / cameras
installer / systemd
backup / restore
layout migration
licensing
config loader
simulation/demo mode
session start/end
customer runtime data paths
```

If a change can lose customer data or break a real installation, it needs a clear backup/rollback plan.
