# AI coding agent instructions

This repository is the source of truth for Hall PTZ Control.

Hall PTZ Control is a Raspberry Pi touchscreen application for controlling VISCA-over-IP PTZ cameras from a visual seating layout.

Current state:

```text
Working application + installable MVP candidate.
Core CLI/installer/systemd/diagnostics/backup/restore/demo foundations exist.
Release-candidate QA and Raspberry Pi hardware validation remain before customer deployment.
```

## Non-negotiable rules

- Do not commit directly to `main`.
- Work from a GitHub issue or focused task whenever possible.
- Before implementing an issue, confirm it satisfies `docs/DEFINITION_OF_READY.md`.
- Keep changes small enough to review.
- Do not create broad refactors unless the issue explicitly asks for them.
- Do not add new dependencies without a clear reason in the PR body.
- Do not commit customer passwords, license keys, private keys, real customer data or sensitive network details.
- Do not add automatic deployment to customer Raspberry Pis.
- Do not install/deploy customer systems from random commits; use tags or approved release-candidate branches.
- Do not change pricing, legal wording, licensing behaviour or customer-facing commercial terms without explicit human review.
- Do not bypass backup/restore/rollback safety for customer data.

## Architecture direction

Prefer this direction for new code and refactors:

```text
domain/          Pure domain models, value objects and constants
application/     Product/application services and use cases
core/            Event bus, controller, state and supervisor
ports/           Interfaces for hardware, storage and external systems
adapters/        Hardware, storage and simulation adapters
ptz/visca/       VISCA protocol, commands, parser, manager and workers
ui/              PyQt interface and view code
runtime/         CLI, installer, systemd and diagnostics
bootstrap.py     Dependency wiring / application composition
```

## Legacy boundaries

- Do not add new business logic to legacy Qt controllers.
- Keep UI code focused on presentation and user interaction.
- Put product behaviour in application/domain services.
- Do not create another camera controller.
- `CameraManager` (`ptz/visca/manager.py`) owns VISCA workers/connections; it is an internal implementation detail of `ViscaCameraAdapter`, not an application-layer boundary.
- `CameraPort` (`ports/camera_port.py`) is the application-level camera interface.
- `ViscaCameraAdapter` (`adapters/visca_camera_adapter.py`) implements `CameraPort` and owns all socket/VISCA details.
- `CameraService` and `ViscaController` have been removed (3.38.x) — do not reference or recreate them.
- Architecture migration complete: application layer uses ports; adapters own hardware/protocol details.
- Temporary architecture exceptions must not become copied patterns.

## Required checks before opening a PR

Run the checks that apply to the change:

```bash
python3 -m pytest
python3 -m ruff check .
```

If architecture/import boundaries are touched:

```bash
python3 -m pytest tests/test_architecture_boundaries.py
```

If runtime, config, diagnostics, installer, support or data paths are touched:

```bash
python3 -m runtime.cli version
python3 -m runtime.cli status
python3 -m runtime.cli doctor
```

If demo/simulation is touched:

```bash
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
python3 -m runtime.cli --profile demo demo reset
python3 sim_mode.py show
```

If backup/restore is touched:

```bash
python3 -m runtime.cli backup
python3 -m runtime.cli restore path/to/test-backup.zip
```

Use test data, not real customer data.

## PR expectations

Every PR should explain:

1. What changed.
2. Which issue it closes, if any.
3. Which commands were run.
4. What was not tested.
5. What risk remains.
6. Whether customer data, backup, restore or rollback is affected.
7. Whether operator/support docs need updating.

Use `.github/pull_request_template.md`.

## Review guidelines

Codex PR reviews must use Spanish for all review summaries, inline comments and follow-up explanations.

Before leaving a PR review comment, verify whether the finding is likely to be a real issue or a false positive:

1. Check the surrounding code, affected tests, configuration, runtime path and existing project conventions.
2. Explain the reasoning in the comment: what could break, why it matters and what evidence supports the finding.
3. State whether the issue is likely real, uncertain or likely a false positive.
4. If uncertain, ask for the smallest missing piece of context instead of presenting the finding as certain.
5. If likely false positive, do not block the PR. Either avoid commenting or clearly mark it as `Posible falso positivo`.
6. Suggest the smallest safe fix when the issue is likely real.
7. Do not leave vague comments such as "check this", "possible bug" or "needs improvement" without a concrete explanation.

Preferred Spanish review comment format:

```text
Tipo: bug real | riesgo | posible falso positivo | mejora no bloqueante
Impacto: <qué podría romperse>
Evidencia: <archivo/línea/comportamiento revisado>
Por qué no parece falso positivo: <razón concreta>
Cambio mínimo sugerido: <acción concreta>
```

For high-risk areas, be stricter and require stronger evidence before approving:

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

## Issue readiness

Before implementation starts, the issue should clearly state:

1. Parent issue, epic or roadmap item.
2. Depends on.
3. Blocks / Related.
4. Acceptance criteria.
5. Status, risk and type.
6. Tests expected.

Use `None` or `not applicable` only when the absence of a dependency, blocker or test requirement is intentional.

## Current priority

Follow the installable/scalable product roadmap and release-candidate direction.

Default order for AI-assisted work:

1. Stabilise release-candidate documentation and backlog state.
2. Runtime/customer data separation from application code.
3. Persistent production logs.
4. Sanitized support bundle export.
5. Seat ID / label / preset / camera role decoupling.
6. Render seat UI from persistent `room_layout.json`.
7. Session start/end/home through `SessionService`.
8. CameraPort / VISCA adapter boundary cleanup.
9. Offline signed licensing foundation.
10. Visual layout editor and advanced features after foundations are safe.

## High-risk areas

Review especially carefully:

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
