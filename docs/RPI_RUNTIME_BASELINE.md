# KH PTZ Control — Raspberry Pi Runtime Baseline

This document is the compatibility matrix for Raspberry Pi installations.
It defines the supported hardware, OS, Python version and dependency policy
for MVP installations and Raspberry Pi release-candidate validation.

**Authoritative source**: this file.  
**Related**: `docs/INSTALL_RPI.md` (step-by-step install), `docs/DEPENDENCY_PINNING_POLICY.md`.  
**Validation gate**: `docs/MVP_VALIDATION_REPORT.md`.

---

## Supported hardware

| Hardware | Status | Notes |
|---|---|---|
| Raspberry Pi 4 Model B (2 GB RAM) | **Supported** — minimum spec | Tested target for MVP. |
| Raspberry Pi 4 Model B (4 GB / 8 GB RAM) | Supported | Preferred for production installs. |
| Raspberry Pi 5 | Supported — not yet validated | Expected to work; #381 validation needed. |
| Raspberry Pi 3 Model B+ | Not supported | Insufficient RAM for PyQt5 UI reliably. |
| Raspberry Pi Zero / CM | Not supported | Insufficient performance. |

**Minimum RAM**: 2 GB.  
**Minimum storage**: 16 GB microSD (Class 10 / A1 or better).

---

## Supported operating system

| OS | Status | Notes |
|---|---|---|
| Raspberry Pi OS Bullseye (Debian 11) 64-bit | **Supported** — recommended | Ships **Python 3.9.2** (the supported target); PyQt5 available via `apt`. |
| Raspberry Pi OS Bookworm (Debian 12) 64-bit | Supported — not validated | Ships Python 3.11; PyQt5 available via `apt`. May work, but 3.9.2 is the validated target. |
| Raspberry Pi OS Bookworm 32-bit | Not validated | May work; not a test target. |
| Ubuntu 22.04 (Pi edition) | Not validated | May work for development; not a support target. |
| Generic Debian 12 (non-Pi) | CI approximation only | Used in GitHub Actions CI; not a customer deployment target. |

**Recommended image**: Raspberry Pi OS Bullseye (Debian 11), 64-bit, **Lite** or **Desktop** depending on display requirements. Bullseye ships the supported Python 3.9.2 target.  
Use the [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to write the image.

---

## Python version

**The single supported target is Python 3.9.2** — the system Python that ships
with Raspberry Pi OS Bullseye (Debian 11) 64-bit. The whole system must run on
3.9.2. The codebase uses `from __future__ import annotations` and avoids 3.10+
runtime syntax (no `match`/`case`, no runtime `X | Y` unions) to stay compatible.

| Python version | Status | Notes |
|---|---|---|
| **3.9.2** | **Supported** — target | Ships with Raspberry Pi OS Bullseye; used in CI. The version the product is built and validated for. |
| 3.9.x (> 3.9.2) | Supported | Same minor line; expected to behave identically. |
| 3.10 / 3.11 / 3.12 | Not validated | May work (code is 3.9-compatible), but not the validated target. Do not assume pilot readiness without re-validating. |
| 3.8 and below | Not supported | Uses `from __future__ import annotations` and other 3.9+ syntax. |

**Install via system package manager.** Do not use `pyenv`, `conda` or `asdf` on production
Pi installs. System Python from `apt` avoids virtualenv conflicts with PyQt5.

---

## System (apt) dependencies

Required on all installs:

```bash
sudo apt update
sudo apt install -y git rsync python3-pyqt5 python3-pyqt5.qtsvg
```

| Package | Version (Bullseye) | Purpose |
|---|---|---|
| `python3-pyqt5` | 5.15.x | PyQt5 GUI framework |
| `python3-pyqt5.qtsvg` | 5.15.x | SVG icon rendering |
| `git` | 2.39.x | Repository clone and update |
| `rsync` | 3.2.x | Application file installation |

Optional for ATEM installs:

```bash
sudo apt install -y python3-pip
pip3 install -r requirements-atem.txt
```

---

## Python (pip) dependencies

**Runtime** (`requirements-rpi.txt`): intentionally empty for Raspberry Pi installs.  
All runtime dependencies are provided by `apt` on Raspberry Pi OS.

**PyYAML and PyQt5** are listed in `requirements.txt` for development machines where
`apt` may not be available (e.g. macOS or Windows dev workstations). On Raspberry Pi,
use the `apt` versions above instead.

```bash
# Raspberry Pi: no pip packages required at runtime
# (PyQt5 installed via apt above)
```

**Optional ATEM** (`requirements-atem.txt`):

```text
PyATEMMax    # Blackmagic ATEM library — MIT licence
```

Install only if `features.atem_enabled: true` in `config.yaml`. If the package is absent,
ATEM monitoring is disabled and the application continues to run.

---

## ATEM dependency policy

| Condition | Behaviour |
|---|---|
| `PyATEMMax` installed and `features.atem_enabled: true` | ATEM connection active |
| `PyATEMMax` installed and `features.atem_enabled: false` | ATEM connection disabled (feature flag wins) |
| `PyATEMMax` not installed | ATEM monitoring disabled; application starts normally; `khptz doctor` reports `ATEM library not available` |

**Rule**: missing `PyATEMMax` must never prevent the application from starting.
The ATEM import is guarded at runtime.

---

## Development and CI approximation

CI uses Ubuntu + Python 3.9 (matching the 3.9.2 target line), which approximates
the Raspberry Pi OS Bullseye Python runtime but is **not** equivalent to real
hardware validation.

| Environment | Approximates | Limitations |
|---|---|---|
| GitHub Actions CI (ubuntu-latest, Python 3.9) | Bullseye Python runtime (3.9.2 target) | No Pi CPU, no real touchscreen, no real camera/ATEM |
| macOS / Windows dev workstation | PyQt5 via pip; use Python 3.9 to match target | Not a deployment target; ATEM and camera hardware not present |
| Real Raspberry Pi 4 (Bullseye, 64-bit, Python 3.9.2) | Production target | Required for #381 MVP validation |

CI passing does **not** imply pilot readiness. Real Raspberry Pi validation through
`#381` is required before claiming pilot/customer readiness.

---

## Runtime version checks (`khptz doctor`)

`khptz doctor` should report incompatible runtime versions. Current checks:

| Check | Pass condition | Failure action |
|---|---|---|
| Python version | exactly 3.9.x | OK on 3.9.x; WARNING on 3.10+ (not validated); FAIL below 3.9 |
| PyQt5 import | Available | FAIL — application cannot start |
| PyQt5 SVG import | Available | WARNING |
| PyATEMMax import | Available when `atem_enabled: true` | WARNING (application still runs) |
| config.yaml readable | Parses without `ConfigError` | FAIL with field_path and remediation |
| Data directory | Writable | WARNING |

---

## Unsupported combinations

| Combination | Reason |
|---|---|
| Python 3.8 on any OS | `from __future__ import annotations` and other 3.9+ syntax used |
| Raspberry Pi OS 32-bit | Not a test or support target |
| Raspberry Pi 3 | Insufficient RAM for reliable PyQt5 UI |
| Docker / containerised Raspberry Pi | Not a supported deployment model |
| Raspberry Pi with non-standard display drivers | `khptz doctor` display check not implemented; treat as not validated |

---

## First-pilot validation target

The #381 Raspberry Pi MVP validation run must use:

```text
Hardware:   Raspberry Pi 4 Model B, 2 GB or 4 GB RAM
OS:         Raspberry Pi OS Bullseye (Debian 11) 64-bit
Python:     3.9.2 (system apt)
PyQt5:      apt package (5.15.x)
Release:    approved release tag or release-candidate branch
Profile:    Starter (1 camera) AND Standard (2 cameras) separately
```

Any deviation from this baseline during validation must be recorded in
`docs/MVP_VALIDATION_REPORT.md` as a known limitation or risk.

---

*See also: `docs/INSTALL_RPI.md`, `docs/DEPENDENCY_PINNING_POLICY.md`, `docs/IMPLEMENTATION_PLAN.md`*
