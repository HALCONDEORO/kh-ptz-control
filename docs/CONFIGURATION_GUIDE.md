# Configuration Guide

This guide explains the current configuration model for KH PTZ Control.

The project is transitioning from legacy root `.txt` files to validated YAML configuration with installation profiles, runtime mode, offline mode and camera registry support.

> Current status: YAML defaults and migration tooling exist. Legacy `.txt` files remain supported as fallback/migration input during the MVP transition.

> MVP validation: before first-pilot/customer readiness, configuration and runtime data paths must be validated on real Raspberry Pi hardware and recorded in `docs/MVP_VALIDATION_REPORT.md`.

---

## Current configuration sources

| Source | Status | Purpose |
|---|---|---|
| `config/defaults/starter.yaml` | current | Starter-style default profile. |
| `config/defaults/standard.yaml` | current | Standard two-camera default profile. |
| `config/defaults/demo.yaml` | current | Demo profile and fake hardware defaults. |
| `config.yaml` | current target | Site/customer runtime configuration after migration or install. |
| Legacy `.txt` files | fallback/migration | Existing deployments and compatibility during transition. |
| `room_layout.json` | current | Room/seats/layout/preset mapping data. |

---

## Configuration rule

Config and layout are separate.

| Area | Owner |
|---|---|
| Hardware, cameras, ATEM, runtime mode, installation ID, profile, offline mode | `config.yaml` / settings |
| Room, seats, labels, presets, camera role, visual positions | `room_layout.json` |
| Names assigned to seats | `seat_names.json` |
| Chairman personal presets | `chairman_presets.json` |

Do not put seat coordinates or customer runtime data into source code.

---

## YAML profile templates

Current templates:

```text
config/defaults/starter.yaml
config/defaults/standard.yaml
config/defaults/demo.yaml
```

Expected use:

- use `starter.yaml` for one-camera installations;
- use `standard.yaml` for two-camera installations;
- use `demo.yaml` for fake hardware and safe demonstration/testing;
- copy or generate a site-specific `config.yaml` during installation;
- never commit real customer config values.

---

## Legacy migration

Migration command:

```bash
python3 -m runtime.cli migrate
```

Optional destination override:

```bash
python3 -m runtime.cli migrate --config /path/to/config.yaml
```

Overwrite existing config only deliberately:

```bash
python3 -m runtime.cli migrate --overwrite
```

Migration rules:

- read legacy `.txt` files if present;
- generate YAML without losing existing values;
- do not overwrite an existing config unless `--overwrite` is explicit;
- keep enough information for support to understand what changed;
- back up customer data before migration on a real installation.

---

## Legacy fallback files

Legacy files may still exist and may be used during transition:

| File | Purpose | Example | Required |
|---|---|---|---|
| `PTZ1IP.txt` | platform camera IP | `172.16.1.11` | yes in legacy mode |
| `PTZ2IP.txt` | comments camera IP | `172.16.1.12` | yes for legacy two-camera installs |
| `config.yaml` `cameras[0].visca_id` | camera 1 VISCA ID | `81` | yes |
| `config.yaml` `cameras[1].visca_id` | camera 2 VISCA ID | `82` | yes for two-camera installs |
| `ATEMIP.txt` | ATEM IP | `192.168.1.240` | no |
| `Contact.txt` | support/contact text | `IT Support` | no |

Do not commit real customer versions of these files.

---

## Example YAML structure

```yaml
site:
  installation_id: "khptz-2026-0007"
  customer_name: "Customer Name"
  room_name: "Main Hall"
  installation_profile: "standard_2_camera"

runtime:
  mode: "production"
  connectivity_mode: "offline"
  data_dir: "~/.config/khptz"
  fullscreen: true

cameras:
  - id: "platform"
    role: "platform"
    protocol: "visca"
    ip: "172.16.1.11"
    port: 5678
    visca_id: "81"
    enabled: true

  - id: "comments"
    role: "comments"
    protocol: "visca"
    ip: "172.16.1.12"
    port: 5678
    visca_id: "82"
    enabled: true

atem:
  enabled: false
  ip: "192.168.1.240"

support:
  contact_text: "IT Support"
```

---

## Installation identity

Every customer install should have stable site metadata:

```yaml
site:
  installation_id: "khptz-2026-0007"
  customer_name: "Customer Name"
  room_name: "Main Hall"
  installation_profile: "standard_2_camera"
```

Rules:

- `installation_id` must be stable after handover;
- backups, support records and future licenses should reference it;
- do not reuse one installation ID across unrelated customer sites;
- demo data should use demo identity, not a real customer identity.

---

## Installation profiles

Current commercial direction:

| Profile | Expected use |
|---|---|
| `starter_1_camera` | Starter package, one PTZ camera. |
| `standard_2_camera` | Standard package, two PTZ cameras. |
| `demo` | Sales/training/testing with fake hardware by default. |
| `custom` | Explicitly marked non-standard deployment. |

Future profiles may include professional or enterprise variants.

---

## Offline mode

Offline-first is the default product direction.

```yaml
runtime:
  connectivity_mode: "offline"
```

In offline mode:

- internet is not required;
- local LAN is still required for real cameras/ATEM;
- online validation must not be required to start;
- missing internet should be `NOT_APPLICABLE`, not an error;
- future online license validation must remain optional.

---

## Demo mode

Demo configuration must remain isolated from production/customer data.

Rules:

- demo profile should use fake camera/ATEM adapters by default;
- demo must not write production `config.yaml` or `room_layout.json`;
- real hardware in demo mode should be blocked unless deliberately overridden for development;
- demo reset should restore known sample data only.

Useful commands:

```bash
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
python3 -m runtime.cli --profile demo demo reset
```

---

## Runtime data

Current legacy-compatible default path:

```text
~/.config/khptz/
```

This name is legacy from the original KHPTZ project and is retained for compatibility while the MVP is being hardened.

Do not rename this path casually. A future KHPTZ-branded path such as the following may be desirable, but only after an explicit migration PR provides backup, migration, validation and rollback:

```text
~/.config/khptz/
```

Common files:

| File | Purpose |
|---|---|
| `seat_names.json` | names assigned to seats |
| `chairman_presets.json` | chairman personal presets |
| `schedule.json` | login/bypass schedule if applicable |
| `room_layout.json` | persistent layout |
| backup ZIPs | manifest-based backups |

Custom path:

```bash
KHPTZ_DATA_DIR=/mnt/usb/khptz python3 main.py
```

Customer runtime data must be backed up before update, migration, restore or rollback.

---

## Validation checklist

For every real installation:

```text
[ ] config file exists or migration path is clear
[ ] installation_id is present and stable
[ ] installation_profile matches package sold
[ ] runtime connectivity mode is explicit
[ ] valid camera IPs
[ ] no duplicate IPs across cameras/ATEM/router
[ ] valid VISCA IDs
[ ] camera count matches profile
[ ] ATEM enabled only if needed
[ ] demo profile does not use production data
[ ] data_dir exists or can be created
[ ] khptz doctor reports expected status
[ ] backup created after configuration
[ ] #381 validation result recorded when claiming MVP/customer readiness
```

Run:

```bash
python3 -m runtime.cli doctor
```

---

## What still needs hardening

- Full removal of legacy root `.txt` dependency from production paths.
- Complete runtime/customer data separation from source code.
- Explicit migration decision for legacy `~/.config/khptz/` path versus future KHPTZ-branded path.
- Stronger config diff/change history for support.
- Offline license fields and plan enforcement.
- More hardware QA for starter/standard profiles.

---

## Final rule

Commercial configuration must be:

```text
explicit
validated
backed up
recoverable
readable by support
safe for offline mode
separate from customer layout data
validated through #381 before customer-readiness claims
```
