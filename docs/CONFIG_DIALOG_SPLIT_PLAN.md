# Config dialog split plan (#894)

> **Status: DONE (2026-07-24, PR #896).** `ui/config_dialog.py` went from
> 3102 → 1159 lines / 120 → 31 methods. All six tabs plus the section builders
> and status strip now live in `ui/config_pages/`. Runtime coverage was added in
> `tests/test_main_window_smoke.py` (builds MainWindow + the split ConfigDialog).
> The record below is kept as the rationale and the template for future splits.
> Remaining: GUI verification of each Settings tab on the Pi.

Phased plan to break `ui/config_dialog.py` (a single `ConfigDialog(QDialog)` of
~3050 lines / ~120 methods) into per-concern page modules, without breaking
existing behaviour. Grounded in the file's real tab structure as of 2026-07-24.

This is planning only. Each phase is a small, separately verified change; do not
attempt the whole split in one pass. The camera/ATEM write path was already
centralised in #893 (`application/camera_config_service.py`), which is a
prerequisite: it means extracting the write-heavy pages cannot reintroduce the
global-mutation bug, because `tests/test_camera_config_boundary.py` forbids it.

## Target architecture

`ConfigDialog` becomes a thin container that builds the `QTabWidget` and delegates
each tab to a module in a new `ui/config_pages/` package. Each page exposes a
builder `build(parent, mw) -> QWidget` (or a small class) that owns its own
widgets and closures. Config writes go through `mw._camera_config` (#893) or the
relevant application service. Re-export shims in `config_dialog.py` keep
`from ui.config_dialog import …` working for callers and tests.

## The six pages (current line ranges in config_dialog.py)

| Tab | Approx. lines | Writes config? | Risk |
|---|---|---|---|
| Test (diagnostics) | 430–527 | No (read-only) | minimal |
| Access | tab 426 | Little (actions → services) | low |
| Data | tab 427 | Little | low |
| Session | tab 422 | No | low |
| ATEM | 1209–1673 | Yes → `set_atem_ip` (#893) | medium |
| Cameras | 574–1208 | Yes → `set_camera_ip` / `set_camera_visca_id` (#893) | high |

Already-standalone section builders that move first as warm-up:
`_build_status_strip`, `_build_second_platform_section`, `_build_sim_section`,
`_build_preset_validation_section`, `_build_atem_automation_section`.

## Sequence (lowest → highest risk)

- **Phase 0 — Scaffolding** (no behaviour change): create `ui/config_pages/`;
  move the already-parameterised `_build_*_section` helpers there first.
- **Phase 1 — Test page** (430–527): read-only, writes nothing → safest place to
  prove the pattern.
- **Phase 2 — Access + Data**: mostly buttons delegating to services.
- **Phase 3 — Session**.
- **Phase 4 — ATEM** (1209–1673): switcher + discovery + automation; writes
  already go through the service.
- **Phase 5 — Cameras** (574–1208): largest, most careful, done last.
- **Phase 6 — Shrink the container**: `_build_ui` ends up assembling tabs only.

## Per-phase protocol (the guardrail)

1. Move one page to its module + a re-export shim in `config_dialog.py`.
2. `python -m ruff check .`; import offscreen; run related unit tests **and the
   isolated startup smoke** (`QT_QPA_PLATFORM=offscreen python -m pytest
   tests/test_main_startup.py`).
3. **Lower** the `ui/config_dialog.py` budget in
   `tests/test_ui_god_object_budget.py` to the new size (the ratchet only moves
   down).
4. **On the Pi / a real GUI**: open Settings → that tab → exercise every control
   (view values, edit + save where applicable, discovery) → `khptz doctor` clean.
5. Commit per phase — only after the tab is verified on the device.

## Why this order

Read-only and low-write pages go first, so a mistake cannot corrupt customer
config. The two write-heavy pages (Cameras, ATEM) go last and already write
through `CameraConfigService`, so extraction cannot reintroduce direct global
mutation — the boundary test enforces it automatically.

## Related

- #893 — `CameraConfigService` (prerequisite), PR #895
- `tests/test_camera_config_boundary.py` — forbids direct `config.CAM*` writes in `ui/`
- `tests/test_ui_god_object_budget.py` — the ratchet lowered at each phase
- ADR-002 / ADR-006 in `docs/ARCHITECTURE_DECISIONS.md`
