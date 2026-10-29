## Summary

What changes?

## Related issue

Closes #

## Change type

- [ ] Bug fix
- [ ] Refactor
- [ ] Tests
- [ ] Documentation
- [ ] Installation/deployment
- [ ] Configuration/layout/licensing
- [ ] Tooling/CI
- [ ] Runtime CLI / diagnostics
- [ ] UI/operator

## Scope

- [ ] MVP foundation
- [ ] Release-candidate QA
- [ ] Post-MVP
- [ ] Future
- [ ] Not applicable

## Automated/local checks

- [ ] `python3 -m pytest` passes
- [ ] `python3 -m ruff check .` passes
- [ ] `python3 -m pytest tests/test_architecture_boundaries.py` passes if architecture/imports are touched
- [ ] GitHub Actions reviewed if applicable

## Runtime / CLI checks

Select what applies:

- [ ] `python3 -m runtime.cli version` passes
- [ ] `python3 -m runtime.cli status` passes
- [ ] `python3 -m runtime.cli doctor` passes
- [ ] `python3 -m runtime.cli backup` tested if backup/data paths are touched
- [ ] `python3 -m runtime.cli restore <backup.zip>` tested if restore/data paths are touched
- [ ] `python3 -m runtime.cli migrate` tested if config migration is touched
- [ ] Not applicable

Runtime notes:

```text

```

## Demo / simulation checks

Select what applies:

- [ ] `python3 -m runtime.cli --profile demo status` passes
- [ ] `python3 -m runtime.cli --profile demo doctor` passes
- [ ] `python3 -m runtime.cli --profile demo demo reset` passes
- [ ] Legacy `sim_mode.py show/off` checked if simulation files are touched
- [ ] Not applicable

Demo/simulation notes:

```text

```

## Manual checks

Select what applies:

- [ ] App starts manually
- [ ] Real mode reviewed on Raspberry Pi
- [ ] systemd service reviewed/tested
- [ ] Installer tested
- [ ] Rollback tested or considered
- [ ] Camera 1 tested
- [ ] Camera 2 tested
- [ ] ATEM tested if applicable
- [ ] UI reviewed at target resolution
- [ ] Touchscreen/tap/long-press behaviour reviewed if UI/operator flow changed
- [ ] Not applicable

Manual test notes:

```text

```

## Risk

- [ ] Low
- [ ] Medium
- [ ] High

Touched areas:

- [ ] VISCA / camera movement
- [ ] ATEM
- [ ] Runtime CLI / diagnostics
- [ ] Configuration
- [ ] Layout / presets / seats
- [ ] Backup / restore / migration
- [ ] Installer / systemd / Raspberry Pi
- [ ] Login / password / security
- [ ] Licensing / commercial plans
- [ ] Demo / production isolation
- [ ] Documentation only

Remaining risk:

```text

```

## Customer data / security

- [ ] No secrets added
- [ ] No private keys added
- [ ] No real customer data added
- [ ] No real customer private IPs added except sanitised examples
- [ ] No automatic deployment to customer Raspberry Pis added
- [ ] Customer/runtime data paths are protected if touched

## Backup / rollback

If this touches data, configuration, installation, update or restore:

- [ ] Backup considered
- [ ] Rollback considered
- [ ] Migration considered
- [ ] Restore safety considered
- [ ] Not applicable

Notes:

```text

```

## Documentation

- [ ] README updated if usage/installation changed
- [ ] docs updated if architecture/config/deployment changed
- [ ] Known limitations updated if applicable
- [ ] Operator/support docs updated if customer-facing behaviour changed
- [ ] Not applicable

## Release checklist

Review `docs/RELEASE_CHECKLIST.md` if this touches:

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

- [ ] Release checklist reviewed if applicable
- [ ] Not applicable

## Special review focus

What should the reviewer inspect most carefully?

```text

```
