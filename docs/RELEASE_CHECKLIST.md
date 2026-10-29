# Release and Safe Installation Checklist

Use this checklist before installing, updating or handing over a version to a customer.

Goal: avoid bringing unvalidated code into a real installation.

Current target:

```text
v0.1.0-installable-mvp
```

> Rule: customer installs should use tagged releases or approved release-candidate branches, not random commits from `main`.

Readiness states:

```text
demo/no-hardware validated
pre-RC smoke passed
Pi validated
pilot-ready
pilot-ready with limitations
not pilot-ready
```

Rules:

- No real Raspberry Pi validation means `not pilot-ready`.
- No support bundle MVP means `not pilot-ready`.
- Demo/no-hardware validation is not pilot/customer readiness.
- #381 is the real Raspberry Pi validation gate.
- #520 is the human pre-RC/release checklist source.
- #27 is mandatory support bundle MVP work before first pilot readiness.
- #288 remains the MVP scope source, not a duplicate checklist.
- Post-MVP/future work should not block pilot readiness unless explicitly promoted into the pilot/customer-required set.

---

## Release type

Select one:

```text
[ ] internal development
[ ] demo
[ ] release candidate
[ ] new installation rehearsal
[ ] customer update
[ ] urgent hotfix
```

---

## Minimum release details

```text
Version/tag:
Commit:
Date:
Owner:
Customer/room if applicable:
Installation ID if applicable:
Runtime profile:
Connectivity mode:
```

---

## Technical validation before release

Before installing or updating:

```text
[ ] pytest passes
[ ] ruff check . passes
[ ] architecture boundary tests pass
[ ] hardware-free smoke test passes when applicable
[ ] shell scripts checked when installer/runtime scripts changed
[ ] dependency audit reviewed if relevant
[ ] no unreviewed changes on main
[ ] README/docs updated if usage or installation changed
[ ] Definition of Done reviewed
```

Current commands:

```bash
python3 -m pytest
python3 -m pytest tests/test_architecture_boundaries.py
python3 -m ruff check .
python3 -m runtime.cli version
python3 -m runtime.cli status
python3 -m runtime.cli doctor
```

---

## CLI/runtime validation

```text
[ ] hallptz version works, or local python3 -m runtime.cli version works
[ ] hallptz status works, or local fallback works
[ ] hallptz doctor works, or local fallback works
[ ] hallptz backup creates a manifest ZIP
[ ] hallptz restore rejects invalid/corrupt backup safely
[ ] sanitized support bundle export is available before first pilot readiness
[ ] demo reset works in demo profile
[ ] migrate command behaves as expected on test data
```

Local fallback commands:

```bash
python3 -m runtime.cli version
python3 -m runtime.cli status
python3 -m runtime.cli doctor
python3 -m runtime.cli backup
python3 -m runtime.cli restore path/to/backup.zip
python3 -m runtime.cli --profile demo demo reset
python3 -m runtime.cli migrate
```

---

## Configuration validation

```text
[ ] selected profile is correct: starter / standard / demo / custom
[ ] installation_id present and recorded
[ ] connectivity_mode explicit
[ ] camera 1 IP checked
[ ] camera 2 IP checked if applicable
[ ] camera 1 VISCA ID checked
[ ] camera 2 VISCA ID checked if applicable
[ ] ATEM required: yes/no
[ ] ATEM IP checked if applicable
[ ] password.enc exists or will be created during installation
[ ] customer config is not committed to the repo
[ ] demo/simulation disabled for production
```

Setup wizard (product installs):

```text
[ ] wizard autostarts on first desktop login after install
[ ] every camera in the room can be entered (Add camera for a 2-camera site)
[ ] added camera keeps a unique id, IP and VISCA address
[ ] operator and administrator passwords set, and different
[ ] hallptz-control starts by itself once the wizard finishes
[ ] repair mode (menu entry) rejects a wrong administrator password
[ ] rejected repair leaves config and both passwords unchanged
[ ] wizard does not reopen on the next login once provisioned
```

Current/fallback files to consider during migration:

```text
config.yaml
config/defaults/starter.yaml
config/defaults/standard.yaml
config/defaults/demo.yaml
PTZ1IP.txt
PTZ2IP.txt
ATEMIP.txt
Contact.txt
password.enc
```

---

## Backup before touching a customer installation

For a new installation:

```text
[ ] initial backup created after configuration
[ ] backup path recorded
[ ] backup manifest verified
```

For an update:

```text
[ ] previous version/tag/commit recorded
[ ] pre-update backup created
[ ] backup manifest verified
[ ] rollback plan clear
[ ] restore tested on non-customer data where practical
```

Do not update without a backup unless there is an explicit emergency.

---

## Raspberry Pi validation

```text
[ ] app starts manually
[ ] app starts from systemd if applicable
[ ] touchscreen responds
[ ] hallptz-control service status checked if installed
[ ] journalctl logs checked
[ ] camera 1 connects
[ ] camera 2 connects if applicable
[ ] ATEM connects if applicable
[ ] ATEM-disabled install does not fail because ATEM is absent
[ ] CALL action tested
[ ] SET/admin action tested only by installer/admin
[ ] left click/tap recalls preset
[ ] right click/long press saves preset where enabled
[ ] Names mode opens/closes safely
[ ] main presets tested
[ ] session start/end tested
[ ] interrupted-session recovery considered after power loss/crash
[ ] auto power-off/inactivity does not interfere with basic test
```

---

## Demo/simulation validation

```text
[ ] demo profile starts diagnostics without real hardware
[ ] demo reset restores known sample data
[ ] demo does not write production config/data
[ ] fake camera status is visible in diagnostics
[ ] fake ATEM status is visible if applicable
[ ] demo/no-hardware validation is recorded as demo evidence, not pilot/customer readiness
[ ] production mode does not show demo controls unexpectedly
[ ] legacy sim_mode.py is off before production-style testing
```

Commands:

```bash
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
python3 -m runtime.cli --profile demo demo reset
python3 sim_mode.py show
python3 sim_mode.py off
```

---

## Restore and rollback validation

```text
[ ] restore from a known-good backup works on test data
[ ] invalid backup is rejected without touching current data
[ ] pre-restore backup is created
[ ] rollback script reviewed for this target image
[ ] source checkout still present on the device (or --source recorded)
[ ] /etc/hallptz/install-state.env names the expected installed and previous refs
[ ] rollback --dry-run reviewed before the real run
[ ] rollback preserves customer/runtime data
[ ] /opt/hallptz contains no files from the newer release after rollback
[ ] /etc/hallptz/.provisioned survives — the setup wizard does NOT re-run
[ ] both passwords still work at login after rollback
[ ] app starts after rollback
[ ] hallptz doctor and hallptz verify-install run after rollback
```

Rollback script:

```text
runtime/installer/rollback.sh
```

---

## Offline-first validation

```text
[ ] system works without internet if customer is offline
[ ] local network works even when internet is unavailable
[ ] online validation is not required to start
[ ] lack of internet is not treated as an error in offline mode
[ ] local camera/ATEM checks still run in offline mode
```

---

## Handover

```text
[ ] operator trained in normal CALL action
[ ] operator knows what not to touch
[ ] admin/setup actions explained only to authorised installer/admin
[ ] known limitations explained
[ ] support details provided
[ ] version/tag/commit recorded
[ ] installation ID recorded
[ ] initial backup recorded
[ ] rollback/update policy explained if applicable
[ ] customer acceptance noted if applicable
```

---

## Do not release criteria

Do not release if any of these apply:

```text
[ ] pytest fails without an accepted explanation
[ ] ruff fails on real issues
[ ] architecture tests fail
[ ] app does not start
[ ] hallptz doctor cannot run
[ ] main camera does not connect in required hardware profile
[ ] real Raspberry Pi validation has not passed for pilot/customer use
[ ] support bundle MVP is unavailable for first pilot readiness
[ ] no backup exists for an update
[ ] restore/rollback is unclear
[ ] demo/simulation mode was left active in production
[ ] data corruption is detected
[ ] configuration changes are not documented
[ ] release notes do not mention known risks
```

---

## Release notes

Record:

```text
Main changes:
Known risks:
Known limitations:
Tests performed:
Hardware used:
Problems found:
Rollback plan:
Final decision: release / do not release
```

---

## Final rule

A customer release must be:

```text
installable
startable
diagnosable
recoverable
explainable to the operator
```

If one of those five is missing, it is not customer-ready.
