# Raspberry Pi Installation Guide

Single, end-to-end guide for a technician-led Raspberry Pi installation,
installation rehearsal or release-candidate QA. It covers prerequisites,
the installer, the systemd service, backup/restore, rollback, post-install
validation, troubleshooting, the manual fallback path and handover.

> **Status:** installable MVP candidate. Use this guide for development,
> Raspberry Pi QA and supervised pilots. Do not treat `main` as a customer
> release. Customer or pilot installs should use an approved release
> candidate, tagged release or offline package that has passed the release
> checklist and the Raspberry Pi validation gate
> (`docs/MVP_VALIDATION_REPORT.md` recording PASS or PASS WITH LIMITATIONS).

---

## Before you start

Record:

```text
Customer/site:
Technician:
Date:
Target release/tag:
Raspberry Pi model:
Raspberry Pi OS version:
Network profile:
Starter/Standard/custom profile:
ATEM used: yes/no
```

Confirm:

- customer permission is in place;
- the Raspberry Pi is the intended target device;
- camera and ATEM network details are available;
- no real customer secrets will be committed to Git;
- backup/rollback expectations are understood.

---

## Hardware requirements

Recommended:

```text
Raspberry Pi 4 or newer
1920x1080 display, preferably touchscreen
VISCA-over-IP PTZ cameras (TCP port 5678)
Stable local network
Suitable power supply
```

Optional:

```text
Blackmagic ATEM if required by the installation
USB drive for offline backup/restore testing
```

---

## Network requirements

- Raspberry Pi and cameras must be on the same LAN or otherwise reachable.
- Use static IPs for cameras and ATEM.
- Avoid depending on internet access for offline installations.
- Confirm no camera shares an IP with another camera, ATEM or router.
- Run local diagnostics (`khptz doctor`) before handover.
- Review the [Raspberry Pi security baseline](RPI_SECURITY_BASELINE.md) before customer/pilot handover.
- Review the [AV device hardening checklist](AV_DEVICE_HARDENING_CHECKLIST.md) for cameras, ATEM, switches and routers.
- For the recommended network/VLAN design, see [Network architecture](NETWORK_ARCHITECTURE.md).

---

## Raspberry Pi baseline and system dependencies

Recommended baseline for current MVP validation:

- Raspberry Pi OS Bullseye (Debian 11) 64-bit on target hardware;
- **Python 3.9.2** (the supported target) available through the OS package
  manager — this is the system Python on Bullseye. Newer 3.10+ may work but is
  not validated;
- PyQt5 installed through `apt` on Raspberry Pi OS;
- local network access to cameras;
- SSH access only when authorised for installation/support.

Install system dependencies:

```bash
sudo apt update
sudo apt install -y git rsync python3-pyqt5 python3-pyqt5.qtsvg python3-yaml \
                    x11-xserver-utils
```

`python3-yaml` is a hard runtime dependency: product mode installs no pip
packages, and `config/loader.py` imports it at module scope, so without it the
application, `khptz doctor` and the wizard's post-provision step all fail with
`ModuleNotFoundError`. `install.sh` now refuses to install without it.

`x11-xserver-utils` provides `xhost`, which the setup wizard uses to grant the
`khptz` service user scoped access to the touchscreen display. Installing it up
front avoids an apt call in the middle of provisioning — which fails on an
offline appliance and rolls the wizard back. It is not needed with
`--gui-mode user`.

See [Raspberry Pi runtime baseline](RPI_RUNTIME_BASELINE.md) for the full
supported hardware/OS/Python matrix, and [Raspberry Pi golden image](RPI_GOLDEN_IMAGE.md)
for preparing a reusable provisioning image.

---

## Get the approved build

For customer or pilot installs, use the approved release/tag named in the
installation plan:

```bash
git clone https://github.com/HALCONDEORO/kh-ptz-control.git khptz
cd khptz
git checkout <approved-tag-or-release-branch>
```

Do not install from an arbitrary `main` commit unless an emergency exception
is explicitly recorded.

> **Keep this checkout on the device.** `install.sh` copies the code into
> `/opt/khptz` with `--exclude='.git'`, so the install directory is a deployed
> artifact with no git history. Updates and rollbacks re-deploy from *this*
> checkout, and `install.sh` records its path in
> `/etc/khptz/install-state.env`. If the checkout is deleted, `rollback.sh`
> needs `--source` and `--to` supplied by hand.

---

## Python dependencies

The installer handles Python dependencies automatically based on mode — you
do **not** normally run `pip` by hand on a product install:

- **Product mode** (default): all runtime dependencies come from `apt`
  (PyQt5/QtSvg installed above). `requirements.txt` is **not** used — it is
  for development machines only. `requirements-rpi.txt` currently lists no
  packages (comments only); the installer checks for a real requirement line
  and only then installs it — and only then requires `python3-pip`. `pip3` is
  deliberately not a product-mode prerequisite.
- **ATEM support**: pass `--atem` to the installer, or install manually:

  ```bash
  sudo apt install -y python3-pip
  pip3 install -r requirements-atem.txt
  ```

- **Development / rehearsal** (manual, not the product installer — or pass
  `--dev` to the installer):

  ```bash
  pip3 install -r requirements.txt
  pip3 install -r requirements-dev.txt
  ```

---

## Configure the installation

Use safe templates as the starting point. Do not commit real customer
configuration. Follow [Configuration guide](CONFIGURATION_GUIDE.md) and the
templates under `config/defaults/`:

```text
config/defaults/starter.yaml
config/defaults/standard.yaml
config/defaults/demo.yaml
```

Migrate legacy `.txt` config into `config.yaml` where appropriate:

```bash
python3 -m runtime.cli migrate
```

### Legacy fallback files

Legacy files may still be present during transition and migration:

| File | Purpose | Example |
|---|---|---|
| `PTZ1IP.txt` | Platform camera IP | `172.16.1.11` |
| `PTZ2IP.txt` | Comments camera IP | `172.16.1.12` |
| `config.yaml` `cameras[0].visca_id` | Camera 1 VISCA ID | `81` |
| `config.yaml` `cameras[1].visca_id` | Camera 2 VISCA ID | `82` |
| `ATEMIP.txt` | Optional ATEM IP | `192.168.1.240` |
| `Contact.txt` | Support/contact text | `IT Support` |

Before first customer use, confirm:

- camera IPs are correct;
- VISCA IDs are correct;
- ATEM is disabled if not used;
- demo/simulation mode is not active;
- customer-specific files are outside Git tracking.

---

## First-run setup (product install)

A product install is configured **on the device**, through the graphical setup
wizard — not by editing files or running password scripts by hand.

`install.sh` copies the starter config, installs the wizard launcher and its
XDG autostart entry, and wires the password-free `/run/khptz` provisioning
channel. `khptz-control.service` gates on `ConditionPathExists=/etc/khptz/.provisioned`,
so it deliberately will **not** start until the wizard has finished.

1. Log in to (or reboot into) the desktop session. The wizard autostarts.
   (A reboot is the reliable option: `install.sh` adds the desktop user to the
   `khptz` group so it can read `/opt/khptz`, and group membership only takes
   effect at the next login.)
2. Work through the pages: room details → cameras → optional ATEM/network →
   passwords → review.
   - **Cameras:** the starter template seeds one camera. Use **Add camera** for
     a two-camera room — `platform` covers the first three seats and `comments`
     the rest. Added cameras are pre-filled with a free VISCA address and the
     next IP on the same subnet; correct them to match the site.
   - **Passwords:** the operator (entry) and administrator passwords are
     independent and must differ.
3. On Review, confirm. The wizard hands the answers to the privileged
   `khptz-provision` oneshot, which writes `/etc/khptz/config.yaml`, both
   encrypted secrets in `/var/lib/khptz/`, the `.provisioned` marker, and then
   starts `khptz-control`.
4. Verify:

   ```bash
   khptz verify-install
   khptz doctor
   ```

To reconfigure later, open **KHPTZ Setup** from the applications menu (that entry
passes `--force`). Repair mode asks for the **current** administrator password
first — desktop access alone is not enough to change cameras or reset the
passwords. A wrong password is rejected by the privileged side and changes
nothing.

The wizard self-suppresses once `/etc/khptz/.provisioned` exists, so the
autostart entry can fire on every login and quietly do nothing.

---

## Access password (manual/dev fallback)

> Product installs set both passwords through the setup wizard above. Use this
> only for a developer install (`install.sh --dev`) or the manual fallback flow.

Create or verify the admin/operator password.

**Development / manual run** (writes under the current user's data dir):

```bash
python3 setup_password.py        # or: python3 -m runtime.setup_password
```

**Product install** — the service runs as the `khptz` user, so the password must
be written where that service reads it, **not** the technician's home. Run the
setup as the service user with the runtime data dir:

```bash
sudo -u khptz KHPTZ_DATA_DIR=/var/lib/khptz python3 -m runtime.setup_password
```

The tool prints `Contrasena guardada en <path>`. Confirm `<path>` is under the
runtime data dir the service uses (`/var/lib/khptz/...`). If you run it as `pi`
without `KHPTZ_DATA_DIR`, `password.enc` lands in `/home/pi/.config/khptz/`
and the service will still start with login blocked.

If `password.enc` is missing or corrupt, login may block access until a valid
password file is created.

Do not ship a customer install with a known default password. Do not commit
`password.enc` or `password.txt`.

---

## Run locally before installing the service

From the repository:

```bash
python3 -m runtime.cli version
python3 -m runtime.cli status
python3 -m runtime.cli doctor
```

Start the app manually only after config has been checked:

```bash
python3 main.py
```

Normal production-style mode opens full-screen. Record any warnings before
moving to service installation.

---

## Check Pi readiness before installing

Run the installer in check mode to validate all prerequisites without writing
any files:

```bash
sudo ./runtime/installer/install.sh --check
```

This outputs a PASS/WARN/FAIL report. Resolve any FAIL items before proceeding.

---

## Install the runtime service

Use the canonical installer script (add `--atem` for ATEM support, `--dev` for
a development checkout):

```bash
sudo ./runtime/installer/install.sh
```

After install:

```bash
khptz verify-install
khptz version
khptz status
khptz doctor
sudo systemctl status khptz-control --no-pager
```

If the `khptz` command is not on `PATH` yet, use the module form
(`python3 -m runtime.cli doctor`).

### systemd autostart validation

```bash
sudo systemctl daemon-reload
sudo systemctl enable khptz-control.service
sudo systemctl start khptz-control.service
sudo systemctl status khptz-control --no-pager
journalctl -u khptz-control -n 100 --no-pager
```

Reboot validation:

```bash
sudo reboot
# after reconnecting:
khptz status
khptz doctor
sudo systemctl status khptz-control --no-pager
```

> Session MUST NOT start automatically on boot — the operator starts it from
> the touchscreen. See `docs/LIFECYCLE_CONTRACT.md`.

---

## First backup

Create a backup after initial configuration and before handover:

```bash
khptz backup
```

Record the backup path and confirm the file exists. Do not copy the backup to
uncontrolled storage without checking customer data and secrets.

### Restore

```bash
python3 -m runtime.cli restore path/to/backup.zip
```

> **Customer rule:** no update, restore, migration or rollback without a
> known-good backup first. See [Backup/restore contract](BACKUP_RESTORE_CONTRACT.md).

---

## Rollback

Rollback script: `runtime/installer/rollback.sh`.

`/opt/khptz` is a deployed copy with no `.git`, so a rollback re-deploys an
older ref from the **source checkout** (e.g. `/home/<user>/khptz`). `install.sh`
records that checkout and the previous ref in `/etc/khptz/install-state.env`;
keep the checkout on the device or rollback will need `--source` and `--to`
passed by hand.

Before relying on rollback for customer work, test it on the target Raspberry
Pi image:

```text
[ ] service stops cleanly
[ ] previous version is re-deployed to /opt/khptz
[ ] /opt/khptz contains no files from the newer release (rsync --delete)
[ ] customer data is preserved
[ ] /etc/khptz/.provisioned survives — the setup wizard does NOT re-run
[ ] both passwords still work at login
[ ] app starts again
[ ] khptz verify-install and khptz doctor pass or report known warnings
```

See [Update and rollback procedure](UPDATE_ROLLBACK.md) for the full procedure.

---

## User data and paths

Current legacy-compatible default path:

```text
~/.config/khptz/
```

This legacy path is still documented because existing code and migration paths
depend on it. Do not rename it casually during customer work; a future
KHPTZ-branded path (`~/.config/khptz/`) must only be introduced through an
explicit migration PR with backup, migration and rollback. See
[Runtime path contract](RUNTIME_PATH_CONTRACT.md).

Common files:

```text
seat_names.json
chairman_presets.json
schedule.json
room_layout.json
```

Custom path (tests/demo):

```bash
KHPTZ_DATA_DIR=/mnt/usb/khptz python3 main.py
```

Do not delete this customer folder without a backup.

---

## Demo and simulation validation

```bash
python3 -m runtime.cli --profile demo status
python3 -m runtime.cli --profile demo doctor
python3 -m runtime.cli --profile demo demo reset
```

Legacy simulation helper still exists:

```bash
python3 sim_mode.py on
python3 main.py
python3 sim_mode.py off
python3 sim_mode.py show
```

Important: legacy simulation can touch legacy IP files. Confirm it is disabled
before production-style testing.

---

## Post-installation validation

```text
[ ] installed version/tag/commit recorded
[ ] app starts manually
[ ] app starts from systemd
[ ] screen responds
[ ] khptz status runs
[ ] khptz doctor runs
[ ] camera 1 connects
[ ] camera 2 connects if applicable
[ ] ATEM connects if applicable
[ ] demo mode does not touch production data
[ ] CALL action works
[ ] SET/admin actions are protected
[ ] main presets work
[ ] session start/end works
[ ] backup created
[ ] restore tested on non-customer data
[ ] rollback tested before customer update
[ ] installation notes saved
```

For MVP release-candidate evidence, copy the relevant result into
`docs/MVP_VALIDATION_REPORT.md` and link any blocking issues.

### One-command deployment validator

`scripts/validate_rpi_deployment.sh` gathers the on-device evidence needed
before an installation can be called done. It is **read-only**: it changes
nothing on the appliance (the legacy cleanup it calls runs in `--dry-run`).
Run it once per reboot so the "after two reboots" criterion is satisfied:

```bash
sudo bash scripts/validate_rpi_deployment.sh --wizard-user khptz
```

Every run also writes a timestamped report under `/var/log/khptz/validation/`
(or the desktop user's home if that path is not writable). It prints per-check
lines and exits non-zero if any `[FAIL]` is recorded:

- `[ OK ]` — the check passed.
- `[WARN]` — non-blocking; note it but it does not fail validation.
- `[FAIL]` — blocking; the installation must **not** be signed off until resolved.

What each section confirms:

| Section | A `[FAIL]` means |
|---|---|
| Startup mechanisms + acceptance checks | A second/legacy PTZ controller still starts, or more than one KH PTZ Control GUI runs |
| Legacy conflicts (cleanup `--dry-run`) | Conflicting startup entries remain to be quarantined |
| Wizard / Qt Bullseye | `Could not parse stylesheet`, or a profile/camera-count or ATEM-IP contradiction in `doctor` |
| X11 / systemd session | Display/D-Bus session error, GUI running as root, or a restart loop |

Do not sign off on "the code exists". Sign off only after two clean reboots
on the room Pi show exactly one KH PTZ Control GUI, `khptz-control`
active, no legacy controller, and no `[FAIL]` — then record the result in
`docs/MVP_VALIDATION_REPORT.md`.

### MVP validation gate

Installation and validation are separate. This guide explains how to install
and run the app; the real MVP validation gate is the Raspberry Pi validation checklist,
with evidence recorded in `docs/MVP_VALIDATION_REPORT.md`. Do not claim
first-pilot/customer readiness unless that report records `PASS` or
`PASS WITH LIMITATIONS` (with accepted limitations and linked follow-up issues).

---

## Manual fallback when the setup wizard fails

If the on-device setup wizard (`khptz setup`) is unavailable or fails mid-flow,
use this manual path instead of improvising.

### 1. Stop and identify the target

```bash
hostname
uname -a
cat /etc/os-release
python3 --version
pwd
```

If you are not certain this is the customer target device, stop and escalate.

### 2. Preserve current state

```bash
khptz version || python3 -m runtime.cli version
khptz status  || python3 -m runtime.cli status
khptz backup  || python3 -m runtime.cli backup
```

If backup fails on a real customer system, stop unless there is an explicitly
accepted emergency.

### 3. Use approved release inputs

Use the same approved release/tag or offline package the wizard would have
used. Do not substitute a random branch or local development checkout. Record:

```text
Approved release/tag:
Source path/package:
Reason for manual fallback:
Wizard failure summary:
```

### 4. Run official Pi-side commands

```bash
sudo ./runtime/installer/install.sh
khptz version
khptz status
khptz doctor
```

For diagnostics-only fallback, do not reinstall — run `khptz version`,
`khptz status`, `khptz doctor` and `sudo systemctl status khptz-control --no-pager`.

### 5. Record handover notes

If the wizard report cannot be generated, fill in `install_notes.md` locally
from `config.example/install_notes.example.md`. Record technician, release/tag,
commands run, backup path, diagnostics result, known warnings and next
action/escalation.

### 6. Stop and escalate if

- the target Raspberry Pi cannot be identified;
- backup fails before a destructive action;
- `khptz doctor` reports unclear failures;
- installer rerun would overwrite customer data;
- restore cannot validate the backup manifest;
- camera movement or preset behaviour is unsafe;
- customer acceptance depends on untested hardware.

---

## Troubleshooting

### PyQt not installed

Symptom: `ModuleNotFoundError: No module named 'PyQt5'`

```bash
sudo apt install -y python3-pyqt5 python3-pyqt5.qtsvg
```

### Camera does not connect

Review `config.yaml` or profile template, `PTZ1IP.txt` / `PTZ2IP.txt` during
legacy fallback, `config.yaml cameras[*].visca_id`, network cable, camera
power, same LAN and IP conflicts. Then run:

```bash
python3 -m runtime.cli doctor
```

### Demo or simulation was left active

```bash
python3 -m runtime.cli --profile demo doctor
python3 sim_mode.py show
python3 sim_mode.py off
```

Check whether `sim_ip_backup.json` exists.

---

## Handover

Before leaving site:

- run `khptz doctor`;
- test representative camera presets;
- confirm session start/end;
- create or verify backup;
- record install notes;
- explain support process;
- record known limitations.

Close the visit with a customer-facing summary and a full
first-install/handover review before leaving the site.

---

## Final rule

An installation is not complete until these exist:

```text
recorded version/tag/commit
reviewed configuration
app starts manually
app starts through systemd if required
khptz doctor completed
main cameras connected
initial backup created
rollback plan known
installation notes saved
MVP validation report completed when claiming release-candidate readiness
```
