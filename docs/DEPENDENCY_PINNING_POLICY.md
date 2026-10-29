# Dependency Pinning Policy

This policy defines how Hall PTZ Control should manage Python dependencies for development, CI and installable releases.

The goal is reproducible customer installs without blocking normal security updates.

## Principles

```text
[ ] development can use controlled version ranges
[ ] CI should test the dependency set used by developers
[ ] release candidates must use a reviewed dependency set
[ ] customer installs must not float to unreviewed latest versions
[ ] security updates should remain easy to review and apply
```

Do not migrate to Poetry, PDM or another packaging system without a separate approved issue.

## Files

Current dependency files:

```text
requirements.txt
requirements-dev.txt
requirements-rpi.txt
requirements-atem.txt
```

Recommended release lock file:

```text
requirements.lock
```

Alternative if pip constraints are preferred:

```text
constraints-release.txt
```

Use one release lock approach consistently. Do not maintain both as active release sources unless a later issue defines the split.

## Development Policy

Development requirements may use controlled ranges where useful.

Rules:

```text
[ ] avoid unbounded high-risk dependencies
[ ] keep runtime dependencies separate from dev-only tools
[ ] document why a new dependency is needed in the PR
[ ] do not add private package indexes or credentials to the repository
```

## CI Policy

CI should install the normal development test set and run:

```bash
python3 -m pytest
python3 -m ruff check .
```

Security checks should run on a schedule and on demand:

```text
pip-audit
Bandit when configured
Dependabot PR checks
```

If a dependency audit fails because of a known accepted limitation, record the reason and follow-up issue. Do not hide the failure by removing the dependency from the scan.

## Release Policy

Before tagging an installable release candidate:

```text
[ ] resolve or document dependency audit findings
[ ] generate the release lock from the reviewed requirements
[ ] install from the lock on a clean test environment
[ ] run release checklist checks
[ ] record the lock file hash or commit
```

Customer-facing installers should install from the release-approved dependency set, not from unrestricted latest packages.

## Raspberry Pi Policy

Raspberry Pi installs should prefer the release-approved dependency set.

Allowed paths:

```text
release package includes requirements.lock
installer references the lock from the validated tag
offline package includes wheels built from the validated lock
```

Do not require internet access for an installation that was sold or validated as offline-capable.

## Dependabot Policy

Dependabot should propose reviewable PRs for:

```text
pip dependencies
GitHub Actions
```

Rules:

```text
[ ] weekly cadence is preferred initially
[ ] no automatic merge at first
[ ] separate GitHub Actions updates from Python dependency updates
[ ] review major updates manually
[ ] regenerate release lock only through a documented release step
```

## Hash-Locked Installs

Hash-locked installs are the target for release artifacts, but they can be introduced after the first policy PR if implementation risk is high.

Follow-up implementation should decide:

```text
[ ] lock generation command
[ ] hash strategy
[ ] wheel cache/offline package strategy
[ ] Raspberry Pi validation command
[ ] how Dependabot updates the lock safely
```

## Follow-Up Implementation

If this policy lands before lock generation exists, create or keep an implementation issue for:

```text
generate release lock file
validate installer consumes release-approved dependencies
document lock regeneration command
```
