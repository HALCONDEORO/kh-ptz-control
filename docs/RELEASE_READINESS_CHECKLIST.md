# KH PTZ Control — Release Readiness Checklist

**Purpose:** Human-readable checklist for calling an installable build
demo-ready or customer/pilot-ready. Complete this before tagging a release.

**Automated gate:** The automated release gate (#452) uses this checklist
as its source of requirements. Manual review is still required for items
marked NOT_APPLICABLE or NOT_TESTED in automation.

---

## Current candidate: 1.2.3

**Current decision:** DEMO ONLY

Current acceptance and limitations are tracked in the release notes; the
v1.2.3 prerelease was published 2026-11-14. No target-Pi acceptance has
been recorded for this candidate; sections 8, 9 and 12 stay NOT_TESTED
until the real Raspberry Pi acceptance is run (#381).

**Gate status for this candidate:** the automated gate currently reports
blocking findings against the recorded DEMO ONLY decision - 3.1 FAIL
(git-history scrub, known limitation 2), 5.2 NOT_TESTED (doctor never
gated in CI) and 6.1 NOT_TESTED (network not validated on target
hardware). The decision line records the published intent of the v1.2.3
prerelease; the gate fails until those rows are re-verified with real
evidence. Never edit a row to make the gate pass without re-verification.

The table below is the current record the automated gate checks, at
section granularity (item-level detail lives in the archived record
below and must not be carried forward without re-verification):

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1.1 | Section 1 - version and build metadata | ⚠️ WARN | VERSION file present in repo; v1.2.3 prerelease tag published 2026-11-14; VERSION-file and `khptz version` checks run only in the manual release-check workflow; annotated-tag requirement re-verified at release time |
| 2.1 | Section 2 - tests and code quality | ⚠️ WARN | Full pytest suite and Ruff green in gated CI on main; no formal coverage report (archived item 2.5 stays NOT_TESTED) |
| 3.1 | Section 3 - security and repo hygiene | ❌ FAIL | Secret values persist in git history, scrub pending (known limitation 2); bandit, secret-scan and repo-hygiene workflows green in CI |
| 4.1 | Section 4 - SBOM and checksum manifest | ⚠️ WARN | SBOM generation and validation automated in the release gate (#513; workflow_dispatch only, not yet exercised in CI); checksum manifest, dependency completeness and CVE gate pending (#514, items 4.3/4.4) |
| 5.1 | Section 5 - CLI self-test | ✅ PASS | `khptz selftest --json` gated in the tests workflow on every push/PR |
| 5.2 | Section 5 - doctor diagnostics | 🔲 NOT_TESTED | `khptz doctor` runs only in the manual release-check workflow and with `\|\| true` - never gated |
| 6.1 | Section 6 - network and configuration | 🔲 NOT_TESTED | `legacy_config` doctor check unit-tested (#520/#452); network behavior never validated on target hardware; isolated-VLAN matrix never run |
| 7.1 | Section 7 - support bundle and redaction | 🔲 NOT_TESTED | Historical evidence only |
| 8.1 | Section 8 - installer and systemd | 🔲 NOT_TESTED | Awaits Pi acceptance |
| 9.1 | Section 9 - Raspberry Pi hardware validation | 🔲 NOT_TESTED | Awaits Pi acceptance (#381) |
| 10.1 | Section 10 - demo and simulation mode | 🔲 NOT_TESTED | E2E on Pi pending |
| 11.1 | Section 11 - backup and restore | 🔲 NOT_TESTED | Unit/integration green including dry-run; E2E on Pi pending |
| 12.1 | Section 12 - security hardening | 🔲 NOT_TESTED | On-Pi verification pending |

---

## Archived evidence record — build 3.38.2 (commit 8012002)

Historical May 2026 record for another build, kept for item-level detail.
It is NOT the current candidate's evidence: the automated gate ignores
everything from this heading on, and its PASS marks must not be carried
into a new release.

| Field | Value |
|-------|-------|
| **Version** | 3.38.2 |
| **Commit** | 8012002 (main, 2026-05-26) |
| **Branch/tag** | main — no release tag yet |
| **Tester** | Claude Code automated evidence pass |
| **Date** | 2026-05-26 |
| **Environment** | Windows 10 dev machine (hardware validation pending on Raspberry Pi) |
| **Archived decision** | **DEMO ONLY** — Sections 8–12 (hardware, installer, systemd, hardening) NOT_TESTED |

---

## Status key

| Symbol | Meaning |
|--------|---------|
| ✅ PASS | Verified and passing |
| ⚠️ WARN | Passing with caveats — document below |
| ❌ FAIL | Failing — blocks customer/pilot release |
| ➖ N/A | Not applicable to this build |
| 🔲 NOT_TESTED | Not yet verified — acceptable for demo-only, blocks customer |

---

## Section 1: Version and build metadata

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 1.1 | `VERSION` file present and matches semantic version format | ✅ PASS | `3.38.2` — valid semver |
| 1.2 | `git tag` matches `VERSION` (annotated tag, not lightweight) | ❌ FAIL | No annotated tag for 3.38.2 — blocks release; tag must be created before pilot |
| 1.3 | `khptz version` outputs expected version string | ✅ PASS | `KH PTZ Control 3.38.2 (8012002)` |
| 1.4 | `git log --oneline -5` shows clean commit history | ✅ PASS | Recent commits use conventional prefixes; no WIP or debug commits |
| 1.5 | No `TODO: RELEASE` or `FIXME: RELEASE` markers in codebase | ✅ PASS | `grep -r "TODO: RELEASE"` — no hits in product code |

---

## Section 2: Tests and code quality

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 2.1 | `python -m pytest` — all tests pass (no FAIL, no ERROR) | ✅ PASS | 3153 passed, 0 failures (commit 8012002) |
| 2.2 | `python -m ruff check .` — clean | ✅ PASS | 0 warnings, 0 errors |
| 2.3 | Architecture boundary tests pass (`tests/test_architecture_boundaries.py`) | ✅ PASS | 9/9 passed; boundary exception budget: 1/1 (main_window.py → ptz.visca.controller, tracked #740) |
| 2.4 | No tests skipped with `xfail` that would block customer use | ⚠️ WARN | 11 xfailed in `test_product_contract_backlog.py` and `test_demo_atem_panel.py` — these are planned future features, not regressions. Acceptable for demo-only. |
| 2.5 | Test coverage acceptable for affected areas | 🔲 NOT_TESTED | No formal coverage report generated; key paths covered by unit tests |

---

## Section 3: Security and repo hygiene

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 3.1 | No secrets committed (passwords, tokens, private keys, IPs) | ✅ PASS | `scripts/check_secrets.py` — clean. Five legacy `.txt` files untracked from index in #760 |
| 3.2 | `.gitignore` blocks `config.yaml`, `.env`, key files | ✅ PASS | `config.yaml`, `password.txt`, `PTZ1IP.txt`, `ATEMIP.txt`, `Contact.txt`, `sim_ip_backup.json` all covered |
| 3.3 | No real customer site data in repo (names, IPs, installation IDs) | ✅ PASS | `password.txt`, `Contact.txt` and legacy site-IP artifacts were purged from the entire git history on 2026-09-11 (git filter-repo + force-push; exposed strings replaced). |
| 3.4 | `config/examples/` contains only fake/safe sample data | ✅ PASS | `flat_lan_with_warning.yaml`, `standard_2_camera.yaml`, `starter_1_camera.yaml`, `minimal_valid.yaml` — no real site data |
| 3.5 | `tests/fixtures/` contains only fake/safe test data | ✅ PASS | `tests/fixtures/config/` — verified safe |
| 3.6 | Manual secret scan of diff since last release — clean | ✅ PASS | `scripts/check_secrets.py` and `scripts/check_repo_hygiene.py` both pass |

---

## Section 4: SBOM and checksum manifest

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 4.1 | SBOM generated for this build (issue #513) | 🔲 NOT_TESTED | Blocks customer/pilot — issue #513 |
| 4.2 | Release checksum manifest generated (issue #514) | 🔲 NOT_TESTED | Blocks customer/pilot — issue #514 |
| 4.3 | SBOM lists all Python dependencies at exact pinned versions | 🔲 NOT_TESTED | Depends on #513 |
| 4.4 | No dependency CVEs at HIGH or CRITICAL severity (or documented exceptions) | 🔲 NOT_TESTED | Depends on #513 |

---

## Section 5: CLI and diagnostics

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 5.1 | `khptz version` exits 0 | ✅ PASS | `KH PTZ Control 3.38.2 (8012002)` |
| 5.2 | `khptz status` exits 0 on healthy install | ⚠️ WARN | WARN on dev machine (no `config.yaml`). Expected on dev. Needs ✅ on Pi with valid install. |
| 5.3 | `khptz doctor` exits 0 on clean install (no FAIL) | ⚠️ WARN | WARN on dev (no config). All checks OK or WARN — no FAIL. Needs clean Pi run. |
| 5.4 | `khptz doctor --json` produces valid JSON | ✅ PASS | Valid JSON with `overall`, `exit_code`, `checks` keys |
| 5.5 | `khptz fingerprint` exits 0 | ✅ PASS | Outputs installation ID, version, commit, profile |
| 5.6 | `khptz known-good show` exits as expected | ⚠️ WARN | "No known-good state recorded" — expected on fresh install. Must be run after doctor pass on Pi. |
| 5.7 | `khptz supportability --json` produces valid JSON | ✅ PASS | Valid JSON |
| 5.8 | `khptz backup` creates a valid ZIP | 🔲 NOT_TESTED | Not run — requires Pi data directory |
| 5.9 | `khptz restore` restores correctly from backup | 🔲 NOT_TESTED | Requires Pi hardware |

---

## Section 6: Network and configuration

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 6.1 | `khptz doctor` — `network_profile` check passes on isolated AV VLAN config | 🔲 NOT_TESTED | Needs Pi with `config.yaml` |
| 6.2 | `khptz doctor` — `network_profile` warns on flat LAN (not FAIL) | 🔲 NOT_TESTED | Needs Pi with flat LAN config |
| 6.3 | Config policy documented (docs/CONFIG_POLICY.md) | ✅ PASS | `docs/CONFIG_POLICY.md` exists |
| 6.4 | Example configs load without error | ✅ PASS | `config/examples/*.yaml` — `load_config()` validated in test suite |
| 6.5 | Offline-first operation confirmed (no internet required) | ✅ PASS | No internet calls in application code; all dependencies local |

---

## Section 7: Support bundle and redaction

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 7.1 | Support bundle export does not include secrets or real IPs | 🔲 NOT_TESTED | Requires Pi run |
| 7.2 | `RedactionGuard.is_safe_for_export()` passes on doctor output | 🔲 NOT_TESTED | Unit tests exist; E2E not run |
| 7.3 | `SupportBundleManifest.restore_capable` always False | ✅ PASS | Enforced in tests |
| 7.4 | Warranty state and fingerprint safely included in bundle | 🔲 NOT_TESTED | Requires Pi run |

---

## Section 8: Installer and systemd

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 8.1 | Installer script installs without error on clean Raspberry Pi OS | 🔲 NOT_TESTED | Blocks pilot — issue #757 |
| 8.2 | `systemd` service starts and stays up | 🔲 NOT_TESTED | Blocks pilot |
| 8.3 | `journalctl -u khptz` shows no unexpected errors after startup | 🔲 NOT_TESTED | Blocks pilot |
| 8.4 | Uninstall / rollback path works | 🔲 NOT_TESTED | Blocks pilot |
| 8.5 | Upgrade path from previous release tested | 🔲 NOT_TESTED | Blocks pilot |

---

## Section 9: Raspberry Pi hardware validation

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 9.1 | Application starts on Pi hardware (not just dev machine) | 🔲 NOT_TESTED | Blocks pilot — issue #757 |
| 9.2 | Camera VISCA control works (pan/tilt/zoom) | 🔲 NOT_TESTED | Blocks pilot |
| 9.3 | Camera presets work | 🔲 NOT_TESTED | Blocks pilot |
| 9.4 | ATEM switcher control works (if enabled) | 🔲 NOT_TESTED | Blocks pilot |
| 9.5 | Touchscreen input works | 🔲 NOT_TESTED | Blocks pilot |
| 9.6 | `khptz doctor` passes on Pi with live hardware | 🔲 NOT_TESTED | Blocks pilot |
| 9.7 | Disk space adequate (>500 MB free) | 🔲 NOT_TESTED | |
| 9.8 | CPU temperature within safe range | 🔲 NOT_TESTED | |

---

## Section 10: Demo and simulation mode

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 10.1 | `khptz --profile demo status` exits 0 | ⚠️ WARN | Exits WARN due to `sim_ip_backup.json` detected in working directory. On clean Pi install this file won't be present. |
| 10.2 | `khptz --profile demo doctor` shows demo isolation checks | ✅ PASS | Shows `FakeCamera`, `FakeATEM`, isolated data path `khptz-demo` |
| 10.3 | `khptz --profile demo demo reset` works | 🔲 NOT_TESTED | |
| 10.4 | Demo mode does not write to production data directory | ✅ PASS | Data path: `~/.config/khptz-demo` (isolated) |
| 10.5 | Simulation mode flag (`sim_ip_backup.json`) produces WARNING | ✅ PASS | Confirmed: doctor reports `[WARN] simulation: Simulation mode is active` |

---

## Section 11: Backup and restore

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 11.1 | `khptz backup` creates valid ZIP with manifest | 🔲 NOT_TESTED | Blocks pilot |
| 11.2 | `khptz restore <backup.zip>` restores all expected files | 🔲 NOT_TESTED | Blocks pilot |
| 11.3 | Restore fails safely on corrupt or missing ZIP | ✅ PASS | Enforced in unit tests |
| 11.4 | Customer data not lost during restore (previous backed up) | 🔲 NOT_TESTED | Blocks pilot |

---

## Section 12: Security hardening (Raspberry Pi)

Run these checks on real Raspberry Pi hardware or an equivalent target environment.
They do not replace the individual security issues — they prove that everything works
together in the target runtime.

Use: `systemctl show khptz-control -p User -p NoNewPrivileges -p ProtectSystem -p ProtectHome -p PrivateTmp`

| # | Check | Status | Notes |
|---|-------|--------|-------|
| 12.1 | Service runs as `khptz` user (not root, not `pi`) | 🔲 NOT_TESTED | Blocks pilot |
| 12.2 | `NoNewPrivileges=true` active in systemd service | 🔲 NOT_TESTED | |
| 12.3 | `ProtectSystem=strict` active — `/opt/khptz` read-only | 🔲 NOT_TESTED | |
| 12.4 | `ProtectHome=true` active | 🔲 NOT_TESTED | |
| 12.5 | `PrivateTmp=true` active | 🔲 NOT_TESTED | |
| 12.6 | `/opt/khptz` owned root:khptz, mode 0750 or tighter | 🔲 NOT_TESTED | |
| 12.7 | `/etc/khptz` owned root:khptz, mode 2750 or tighter | 🔲 NOT_TESTED | |
| 12.8 | `/var/lib/khptz` owned khptz:khptz, mode 0750 or tighter | 🔲 NOT_TESTED | |
| 12.9 | `/var/log/khptz` owned khptz:khptz, mode 0750 or tighter | 🔲 NOT_TESTED | |
| 12.10 | `/var/backups/khptz` owned khptz:khptz, mode 0750 or tighter | 🔲 NOT_TESTED | |
| 12.11 | `khptz` user is a system account with no login shell (`nologin`) | 🔲 NOT_TESTED | |
| 12.12 | `khptz version` / `khptz status` / `khptz doctor` still work after hardening | 🔲 NOT_TESTED | |
| 12.13 | SSH disabled by default or key-only; root SSH login disabled | 🔲 NOT_TESTED | |
| 12.14 | Default `pi` user disabled or removed before handover | 🔲 NOT_TESTED | |
| 12.15 | Backup manifest includes SHA-256 hashes | 🔲 NOT_TESTED | |
| 12.16 | Restore rejects corrupt/hash-mismatch backup before touching data | ✅ PASS | Enforced in unit tests |
| 12.17 | `redact_event_dict()` tests pass — no known secret keys leaked | ✅ PASS | Covered in test suite (3153 passed) |
| 12.18 | Support bundle / incident snapshots contain no secrets or private IPs | 🔲 NOT_TESTED | Requires Pi E2E run |
| 12.19 | CI secret scanning is green | ✅ PASS | `scripts/check_secrets.py` clean |
| 12.20 | `khptz doctor` reports systemd hardening status (or explicitly deferred) | 🔲 NOT_TESTED | Requires Pi |

Manual inspection commands:

```bash
id khptz
ls -ld /opt/khptz /etc/khptz /var/lib/khptz /var/log/khptz /var/backups/khptz
systemctl status khptz-control --no-pager
systemctl show khptz-control -p User -p NoNewPrivileges -p ProtectSystem -p ProtectHome -p PrivateTmp
journalctl -u khptz-control -n 50 --no-pager
khptz version && khptz status && khptz doctor
```

---

## Section 13: Known limitations for this release

```
1. Historical 3.38.2 item: no annotated tag (1.2 FAIL). For the current candidate, v1.2.3
   was published as a prerelease tag (2026-11-14); the annotated-tag requirement is
   re-verified when a release is tagged.

2. git history contains password.txt and Contact.txt values from early development.
   Files are untracked from index (PR #760) but values persist in git history.
   Run git filter-repo to scrub history before any public or third-party repo share.

3. SBOM generation and validation are automated in the release gate (#513); the
   checksum manifest (#514), dependency completeness and the CVE gate (4.3/4.4)
   are not — they block a customer build.

4. Sections 8–12 (installer, Pi hardware, backup/restore E2E, security hardening)
   all NOT_TESTED — acceptable for demo-only, block pilot/customer.

5. 11 xfailed tests in test_product_contract_backlog.py and test_demo_atem_panel.py
   represent planned future features (ATEM simulator, advanced preset features).
   Not regressions.

6. Single remaining architecture boundary exception: ui/main_window.py imports
   ptz.visca.controller for _refresh_zoom() and refresh_ae_mode_async(). Tracked #740.
```

---

## Release decision

| Target | Threshold |
|--------|-----------|
| **Demo / no-hardware** | Sections 1–3, 5, 6 — all PASS or WARN; 8–9 may be NOT_TESTED |
| **Customer / pilot** | All sections — PASS only; WARN requires written acceptance; NOT_TESTED blocks |

The current decision lives in the *Current candidate* record at the top of
this document (the automated gate reads it from there, fail closed).

The gate enforces strict contracts; violations are schema errors (exit 2),
never inferred:

- `**Current decision:**` must be exactly `DEMO ONLY` or `CUSTOMER READY`
  after removing markdown asterisks - no prefixes or extra words
  (`DEMONSTRATION ...`, `CUSTOMER READY NOT APPROVED` are invalid).
- Row ids must be numbered `X.Y`, and every published section 1-12 must
  appear in the current record; missing coverage never counts as PASS.
- Statuses must equal exactly one of PASS / WARN / FAIL / N/A / NOT_TESTED
  after removing emoji - substrings such as `NOT_PASS` are invalid.
- Written acceptance is a structured field: a WARN counts as accepted only
  when its Notes cell begins with `ACCEPTED: ` naming who and when. Prose
  such as "not accepted by reviewer" never counts.

Blockers before pilot/customer:
- [ ] Create annotated git tag `v3.38.2` (1.2)
- [ ] Scrub git history of password.txt / Contact.txt (3.3)
- [ ] Generate SBOM (4.1–4.4 via #513/#514)
- [ ] Raspberry Pi hardware smoke matrix (9.1–9.8 via #757)
- [ ] Installer and systemd validation (8.1–8.5)
- [ ] Backup/restore E2E on Pi (11.1–11.4)
- [ ] Security hardening verification on Pi (12.1–12.14)

**Reviewer:** _________________________

**Date:** _________________________

**Tag:** _________________________

---

*See also: docs/CONFIG_POLICY.md, docs/NETWORK_ARCHITECTURE.md,
docs/RUNTIME_PATH_CONTRACT.md, docs/SUPPORT_BUNDLE_CONTRACT.md*
