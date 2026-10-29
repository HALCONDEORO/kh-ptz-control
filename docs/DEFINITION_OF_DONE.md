# Definition of Done

This document defines when work is complete enough to close an issue or merge a PR.

The goal is to avoid half-finished work, hidden regressions and unsafe customer changes.

---

## Global Definition of Done

A task is done only when the relevant items below are true:

- The code, documentation or planning change is complete.
- Tests are added, or the PR/issue explains why tests do not apply.
- `python3 -m pytest` passes locally or in CI.
- `python3 -m ruff check .` passes, or the reason is documented.
- Normal app startup is not broken.
- Simulation/demo startup is not broken when touched.
- `python3 -m runtime.cli doctor` is considered when runtime, config, diagnostics, install or support behaviour changes.
- README or docs are updated when behaviour, setup or operation changes.
- No customer secrets, private keys or sensitive real customer data are committed.
- No new business logic is added to legacy Qt controllers unless explicitly accepted.
- Config/data changes consider migration and recovery.
- Installer/update/restore changes consider backup and rollback safety.
- Customer-facing changes can be explained simply to operator/support.

---

## Area-specific rules

### Architecture

- New business logic should live in application/domain services, not legacy UI controllers.
- Domain/application code should not depend on PyQt.
- Hardware adapters should not leak into pure domain logic.
- Temporary architecture exceptions must be explicit and removable.
- If a change adds new UI-to-hardware shortcuts, the PR must justify why a service/port path was not used.

### Configuration

- Valid config loads successfully.
- Missing or invalid config fails clearly or falls back deliberately.
- Defaults are explicit.
- Legacy migration is considered when changing config paths or formats.
- Site metadata, installation profile and connectivity mode remain explicit where relevant.
- Real customer config must not be committed.

### Layout and customer data

- Schema version is considered.
- Missing/corrupt file behaviour is defined.
- Backup/import/export impact is considered.
- Active customer data must not be overwritten without a backup path.
- Seat identity, visible label, preset and camera role must not be accidentally coupled in new work.

### Runtime CLI and diagnostics

For changes touching CLI, diagnostics, config loading, runtime modes or support workflows:

```bash
python3 -m runtime.cli version
python3 -m runtime.cli status
python3 -m runtime.cli doctor
```

Where relevant, also check:

```bash
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
```

The PR must say whether these commands were run or why not.

### Deployment

- Installer/systemd changes are repeatable where possible.
- Running an installer twice should not destroy customer data.
- Failure messages should be clear enough for support.
- Rollback impact is considered when changing install/update paths.
- Customer installs should use tags/release candidates, not random commits.

### Diagnostics and readiness

Use the common severity values:

```text
OK
WARNING
ERROR
NOT_APPLICABLE
```

Diagnostics should detect and report first. Automatic repair should only be added in a separate safe issue.

### Backup and restore

- Restore validates the backup before writing files.
- Restore creates a pre-restore backup where practical.
- Unknown ZIP paths are not restored.
- License files, active config and golden backups are protected.
- Backup/restore changes should include tests or a manual validation note.

### Demo and simulation

- Demo mode must not touch production/customer data.
- Demo reset must only reset demo/sample data.
- Legacy `sim_mode.py` side effects must be considered if touched.
- Fake camera/ATEM behaviour must remain visibly separate from real hardware.

### Licensing and security

- Private signing keys are never committed.
- License failure/degraded behaviour is explicit.
- Offline mode must not attempt online validation.
- License or support-bundle changes must not expose secrets.

---

## PR checklist

Use this as a minimum PR checklist:

```text
- [ ] Tests added or not applicable
- [ ] python3 -m pytest passes
- [ ] python3 -m ruff check . passes or reason documented
- [ ] Normal startup considered
- [ ] Simulation/demo impact considered
- [ ] khptz doctor/status considered if runtime/config/diagnostics changed
- [ ] Docs updated if behaviour changed
- [ ] No secrets/private keys/customer-sensitive data committed
- [ ] Data migration/recovery considered if applicable
- [ ] Backup safety considered if installer/restore/data paths changed
- [ ] Rollback impact considered if install/update path changed
- [ ] Operator/support impact considered if customer-facing behaviour changed
```

---

## Release-sensitive changes

If a PR touches any of these areas, review `docs/RELEASE_CHECKLIST.md` before merging:

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

---

## Rule

If the change cannot be safely explained, tested or recovered, it is not done.