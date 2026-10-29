# KH PTZ Control — config.yaml Schema Reference

This document is the canonical reference for `config.yaml`.  
**Source of truth**: `config/settings.py` (types) + `config/loader.py` (validation).  
**Policy**: `docs/CONFIG_POLICY.md`.  
**Usage guide**: `docs/CONFIGURATION_GUIDE.md`.

---

## Overview

`config.yaml` contains hardware, site identity, runtime flags and feature gates for one
customer installation.  It is written once during setup, backed up via `khptz backup`, and
read at startup by `config.loader.load_config()`.

What `config.yaml` is **not**:

| Not config.yaml | Correct file |
|---|---|
| Seat labels / room layout | `room_layout.json` |
| Chairman personal presets | `chairman_presets.json` |
| Attendee name assignments | `seat_names.json` |
| Session schedule | `schedule.json` |
| Secrets / private keys | Never committed anywhere |

---

## Top-level sections

| Section | Required | Description |
|---|---|---|
| `cameras` | **yes** | List of PTZ camera entries. At least one required. |
| `site` | no | Installation identity metadata. |
| `atem` | no | ATEM video switcher connection. |
| `runtime` | no | Runtime mode and data path overrides. |
| `features` | no | Feature flags for the installation. |
| `network` | no | Site network profile (informational). |

---

## `site` — installation identity

All fields optional; empty string when absent.

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `name` | string | no | Venue or customer name (human-readable). | `"Example Hall A"` |
| `contact` | string | no | Support contact text shown in diagnostics. | `"AV Support Team"` |
| `installation_profile` | string | no | Profile key (`starter_1_camera`, `standard_2_camera`, `demo`, `custom`). | `"standard_2_camera"` |
| `installation_id` | string | no | Stable unique ID for this installation. Must be set before customer handover. | `"khptz-2026-0001"` |

**Rules:**

- `installation_id` must be stable after handover; do not change it.
- `installation_profile` must match the package sold to the customer.
- Do not use real customer names in test fixtures or example files.

---

## `cameras` — PTZ camera list

**Required.** At least one entry must be present.

Each entry is an object with these fields:

| Field | Type | Required | Constraints | Description | Example |
|---|---|---|---|---|---|
| `id` | string | **yes** | Unique across all cameras | Logical identifier used in layout and log references. | `"platform"` |
| `role` | string | **yes** | Non-empty | Camera role (`platform`, `comments`, or custom). | `"platform"` |
| `ip` | string | **yes** | Valid IPv4, unique | Camera IP address on the AV network. | `"192.168.30.20"` |
| `visca_id` | string | **yes** | Two hex digits, unique | VISCA camera address byte. First camera is `"81"`, second `"82"`. | `"81"` |

**Validation errors:**

| Condition | field_path | remediation |
|---|---|---|
| `cameras` not a list | `cameras` | Must be a YAML list of camera objects |
| Empty list | `cameras` | Add at least one camera entry |
| Entry not an object | `cameras[N]` | Each entry must have `id`, `role`, `ip`, `visca_id` |
| Missing required field | `cameras[N].FIELD` | Add the missing field |
| Empty field value | `cameras[N].FIELD` | Field cannot be empty |
| Duplicate `id` | `cameras[N].id` | Each camera must have a unique `id` |
| Invalid IPv4 | `cameras[N].ip` | Use a valid IPv4 address, e.g. `192.168.30.20` |
| Duplicate IP | `cameras[N].ip` | Each camera must have a distinct IP address |
| Invalid `visca_id` | `cameras[N].visca_id` | Must be a two-digit hex byte, e.g. `"81"` |
| Duplicate `visca_id` | `cameras[N].visca_id` | Each camera must have a distinct VISCA ID |

**Example (one camera):**

```yaml
cameras:
  - id: platform
    role: platform
    ip: "192.168.30.20"
    visca_id: "81"
```

**Example (two cameras):**

```yaml
cameras:
  - id: platform
    role: platform
    ip: "192.168.30.20"
    visca_id: "81"
  - id: comments
    role: comments
    ip: "192.168.30.21"
    visca_id: "82"
```

---

## `atem` — ATEM video switcher

Optional. All fields default to empty string.

| Field | Type | Required | Description | Example |
|---|---|---|---|---|
| `ip` | string | no | ATEM switcher IP address. Empty string disables ATEM. | `"192.168.30.30"` |

Enable ATEM integration via `features.atem_enabled: true`.

---

## `runtime` — runtime mode

Optional. All fields have safe defaults.

| Field | Type | Default | Description |
|---|---|---|---|
| `data_dir` | string | `""` | Override for the data directory. Empty = use the system default (`KHPTZ_DATA_DIR` env or `/var/lib/khptz`). |
| `connectivity_mode` | string | `"offline"` | `"offline"` (no internet required) or future `"online"`. |
| `mode` | string | `"production"` | `"production"`, `"demo"` or `"development"`. |

**Rules:**

- Do not put secrets or private keys in `runtime`.
- `data_dir` override in config is legacy; prefer the `KHPTZ_DATA_DIR` environment variable for new installs.
- `connectivity_mode` must be `"offline"` for customer installations (online validation is future work).

---

## `features` — feature flags

Optional. All flags default to `false`.

| Field | Type | Default | Description |
|---|---|---|---|
| `atem_enabled` | bool | `false` | Enable ATEM connection. Requires `atem.ip`. |
| `simulation` | bool | `false` | Use fake hardware adapters (demo/development only). |
| `allow_real_hardware_in_demo` | bool | `false` | Allow real cameras/ATEM to be used during demo mode. Development use only. |

**Boolean parsing rules:**

All boolean fields accept `true`/`false`, `yes`/`no`, `1`/`0` (case-insensitive), or native YAML `true`/`false`.  
Any other value raises a `ConfigError` with `severity="error"`.

---

## `network` — site network profile

Optional. Informational only — does not affect runtime behaviour directly.

| Field | Type | Default | Description | Example |
|---|---|---|---|---|
| `profile` | string | `"unknown"` | `"isolated_av_vlan"`, `"flat_lan"`, or `"unknown"`. | `"isolated_av_vlan"` |
| `av_subnet` | string | `""` | AV subnet in CIDR notation. | `"192.168.30.0/24"` |
| `av_vlan_id` | string | `""` | VLAN ID for the AV network. | `"30"` |
| `guest_access_allowed` | bool\|null | `null` | Whether guest devices can reach the AV network. `null` = unknown. | `false` |
| `internet_required` | bool | `false` | Whether internet access is required for normal operation. | `false` |
| `static_ips` | bool\|null | `null` | Whether static IPs are used for cameras/ATEM. `null` = unknown. | `true` |
| `notes` | string | `""` | Free-text notes for support/handover. | `"Managed switch on rack 2"` |

---

## Secrets — explicitly excluded

The following must **never** appear in `config.yaml`:

- Passwords or PINs (stored in `password.enc` via `SecretManager`)
- Private keys or signing keys
- API tokens or cloud credentials
- Customer personal data beyond site name and contact text

See `docs/CONFIG_POLICY.md` for the full policy.

---

## Validation error structure

`ConfigError` (from `config.loader`) carries structured fields:

| Attribute | Type | Description |
|---|---|---|
| `args[0]` | string | Human-readable error message (also passed to `str(exc)`). |
| `field_path` | string | Dot-path to the offending field, e.g. `cameras[0].ip`. |
| `severity` | string | `"error"` (blocks startup), `"warning"` (degraded), or `"info"`. |
| `remediation` | string | Short installer-facing instruction for fixing the problem. |

Current loader only raises `severity="error"`.  Future work may add `"warning"` for degraded
configurations (e.g. ATEM enabled but IP empty).

---

## Legacy `.txt` → `config.yaml` migration mapping

The legacy configuration format used plain `.txt` files in the project root.
The `khptz migrate` command reads these and writes a `config.yaml`.

| Legacy file | `config.yaml` field | Notes |
|---|---|---|
| `PTZ1IP.txt` | `cameras[0].ip` | First camera (platform role). Default `172.16.1.11`. |
| ~~`Cam1ID.txt`~~ (removed) | `cameras[0].visca_id` | First camera VISCA ID. Default `81`. Migrated via `khptz migrate`. |
| `PTZ2IP.txt` | `cameras[1].ip` | Second camera (comments role). Omitted if file absent. |
| ~~`Cam2ID.txt`~~ (removed) | `cameras[1].visca_id` | Second camera VISCA ID. Default `82`. Migrated via `khptz migrate`. |
| `ATEMIP.txt` | `atem.ip` + `features.atem_enabled` | ATEM IP. `atem_enabled` set to `true` when non-empty. |
| `Contact.txt` | `site.contact` | Support contact text. |

Migration command:

```bash
python3 -m runtime.cli migrate
python3 -m runtime.cli migrate --overwrite   # overwrite existing config.yaml
```

Legacy files are **not** deleted by migration. They remain as fallback until explicitly removed.

See `docs/CONFIGURATION_GUIDE.md` for the full migration workflow.

---

## Complete annotated example (Standard, 2 cameras)

```yaml
# KH PTZ Control — customer config.yaml
# Generated by: khptz migrate / manual setup
# Profile: standard_2_camera

site:
  name: "Example Hall A"              # venue / customer name
  contact: "AV Support +44 20 0000"   # shown in diagnostics
  installation_profile: "standard_2_camera"
  installation_id: "khptz-2026-0001"   # stable — do not change after handover

cameras:
  - id: platform                      # logical name — referenced in room_layout.json
    role: platform
    ip: "192.168.30.20"               # static IP on AV VLAN
    visca_id: "81"                    # VISCA address byte
  - id: comments
    role: comments
    ip: "192.168.30.21"
    visca_id: "82"

atem:
  ip: "192.168.30.30"                 # empty string to disable

runtime:
  connectivity_mode: "offline"        # offline-first; internet not required

features:
  atem_enabled: true                  # set false if ATEM not present
  simulation: false                   # never true on a customer install

network:
  profile: "isolated_av_vlan"
  av_subnet: "192.168.30.0/24"
  av_vlan_id: "30"
  guest_access_allowed: false
  internet_required: false
  static_ips: true
```

---

## Loader API

```python
from config.loader import load_config, ConfigError
from pathlib import Path

try:
    settings = load_config(Path("config.yaml"))
except FileNotFoundError:
    ...   # config not present
except ConfigError as exc:
    print(f"[{exc.severity}] {exc.field_path}: {exc}")
    print(f"Fix: {exc.remediation}")
```

`load_config()` raises:

| Exception | Condition |
|---|---|
| `FileNotFoundError` | File does not exist |
| `yaml.YAMLError` | File is not valid YAML |
| `ConfigError` | Field-level validation failure |

On success it returns a fully validated, typed `AppSettings` object.  
Raw dicts are never returned to callers.

---

*See also: `docs/CONFIGURATION_GUIDE.md`, `docs/CONFIG_POLICY.md`, `docs/RUNTIME_PATH_CONTRACT.md`*
