# Release Process

This process defines how Hall PTZ Control becomes a tagged, traceable, installable release.

## Rule

Customer and pilot Raspberry Pis should be installed or updated only from:

- approved release-candidate branches;
- signed-off tags;
- approved offline packages created from a known tag or release-candidate commit.

Do not install customer systems from arbitrary `main` commits.

## Release Names

Use predictable names:

```text
v0.1.0-rc1
v0.1.0-installable-mvp
v0.1.1-hotfix
v0.2.0
```

The current commercial release target is:

```text
v0.1.0-installable-mvp
```

## MVP Release Gate

The first MVP release must not be called customer-ready until:

- release checks have been run and recorded;
- `python3 -m pytest` passes;
- `python3 -m ruff check .` passes;
- installer and systemd paths are validated or explicitly limited;
- backup and restore are validated on non-customer data;
- #381 Raspberry Pi validation records PASS or PASS WITH LIMITATIONS;
- #27 support bundle MVP work is available before first pilot readiness;
- `docs/MVP_VALIDATION_REPORT.md` records the validation evidence;
- known limitations are updated;
- rollback path is documented.

Readiness wording must stay precise:

```text
demo/no-hardware validated
pre-RC smoke passed
Pi validated
pilot-ready
pilot-ready with limitations
not pilot-ready
```

No real Raspberry Pi validation means `not pilot-ready`. No support bundle MVP means `not pilot-ready`. Demo/no-hardware validation is useful but cannot be presented as pilot/customer readiness.

## Dependency And Repository Controls

Before an installable customer/pilot release, review:

- [Dependency pinning policy](DEPENDENCY_PINNING_POLICY.md)
- [Branch protection policy](BRANCH_PROTECTION_POLICY.md)

The release should use a reviewed dependency set. Do not let customer installs float to unreviewed latest packages after validation.

## Pre-Tag Checklist

Before creating a tag:

```text
[ ] VERSION contains the intended release version.
[ ] CHANGELOG or release notes are updated.
[ ] docs/KNOWN_LIMITATIONS.md is current.
[ ] docs/RELEASE_CHECKLIST.md has been reviewed.
[ ] docs/MVP_VALIDATION_REPORT.md is filled for customer/pilot readiness.
[ ] GitHub Actions are reviewed.
[ ] Release-check workflow or local equivalent has run.
[ ] Backup and restore result is recorded.
[ ] Rollback note is written.
[ ] Commit hash is recorded.
```

## Required Commands

Run the checks that apply:

```bash
python3 -m pytest
python3 -m ruff check .
python3 -m pytest tests/test_architecture_boundaries.py
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

## Release Notes Template

```md
# <tag>

## Summary

## Added

## Fixed

## Changed

## Deployment Notes

## Validation

- Git commit:
- VERSION:
- Release-check result:
- Raspberry Pi validation issue: #381
- MVP validation report:

## Known Limitations

## Backup / Restore

## Rollback

## Customer Data / Security
```

## Create the Tag

Only tag the commit that was validated:

```bash
git status --short
git rev-parse HEAD
git tag -a <tag> -m "<tag>"
git push origin <tag>
```

Do not tag a dirty or unvalidated worktree for customer release.

## Emergency Hotfix

Emergency hotfixes must still be traceable:

- record the customer impact;
- create a focused branch;
- run the smallest safe checks plus any affected-area checks;
- create a tag such as `v0.1.1-hotfix`;
- document what was not tested;
- document rollback.

## Rollback Note

Every customer-facing release should state:

- previous known-good tag;
- whether data migration occurred;
- whether restore is required;
- rollback command or documented manual path;
- what data must be backed up first.

## Installed Version

Support must be able to check the installed version without reading Git manually:

```bash
hallptz version
python3 -m runtime.cli version
cat VERSION
```

The app UI or diagnostics should also expose version information where available.
