# Raspberry Pi Golden Image and Provisioning Checklist

Use this checklist to prepare a new Raspberry Pi for Hall PTZ Control.
A technician must be able to follow this document on site without guessing.

---

## Hardware requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Model     | Raspberry Pi 4 Model B 4 GB | RPi 4 or 5, 4–8 GB RAM |
| Display   | 1920×1080 HDMI or DSI touchscreen | Official 7" DSI or HDMI touchscreen |
| Storage   | 16 GB microSD (Class 10) | 32 GB+ A2-rated card |
| Network   | Ethernet to camera subnet | Ethernet (not Wi-Fi for VISCA reliability) |

---

## OS and base image

- **OS**: Raspberry Pi OS (Bullseye, Debian 11, 64-bit, Lite or Desktop)
- **Version**: Bullseye image shipping the supported **Python 3.9.2** target
  (see [Raspberry Pi runtime baseline](RPI_RUNTIME_BASELINE.md)). Bookworm/3.11
  is **not** validated — do not provision it for a pilot without re-validation.
- **User**: `pi` (default) — do not rename unless you update all scripts
- **Hostname**: `hallptz-control` (optional, helps identify on network)

Do **not** bake customer-specific passwords, IPs or names into the base image.
Apply those after provisioning using the configuration steps below.

---

## Phase 1 — OS setup

Run on the freshly flashed Pi:

```bash
# 1. Update system
sudo apt update && sudo apt full-upgrade -y

# 2. Set locale and timezone (adjust for site)
sudo raspi-config nonint do_change_locale en_GB.UTF-8
sudo timedatectl set-timezone Europe/Dublin

# 3. Enable SSH (for support access)
sudo systemctl enable ssh
sudo systemctl start ssh

# 4. Disable screen blanking (always-on display)
sudo raspi-config nonint do_blanking 1
```

---

## Phase 2 — System dependencies

```bash
# Python and Qt
sudo apt install -y \
    python3 python3-pip python3-venv \
    python3-pyqt5 python3-pyqt5.qtsvg \
    libqt5multimedia5-plugins \
    fonts-ibm-plex

# Networking tools (for camera discovery diagnostics)
sudo apt install -y net-tools nmap arp-scan
```

**ATEM support** (optional — install only if ATEM switcher is in use):

```bash
sudo pip3 install PyATEMMax
```

> On Bullseye (pip 20.3.4) there is no PEP 668 externally-managed marker, so the
> plain command works. Do **not** add `--break-system-packages`: that flag only
> exists in the newer pip shipped on Bookworm and aborts on Bullseye.

---

## Phase 3 — App installation

```bash
# Clone the repository (use a tagged release)
cd /home/pi
git clone https://github.com/HALCONDEORO/legacy-ptz-controller.git hallptz
cd hallptz
git checkout v3.x.y    # replace with the target release tag

# Run the installer
sudo bash runtime/installer/install.sh
```

The installer will:
- Create runtime data directories.
- Install the systemd service (`hallptz-control.service`).
- Enable the service on boot.

Verify with:

```bash
systemctl status hallptz-control
```

---

## Phase 4 — Customer configuration

Apply site-specific configuration **after** the base image is complete.
Never bake these into a shared golden image.

| File | Purpose |
|------|---------|
| `PTZ1IP.txt` | Platform camera IP (e.g. `172.16.1.11`) |
| `PTZ2IP.txt` | Comments camera IP (e.g. `172.16.1.12`) |
| `config.yaml` `cameras[0].visca_id` | Platform camera VISCA ID (e.g. `81`) |
| `config.yaml` `cameras[1].visca_id` | Comments camera VISCA ID (e.g. `82`) |
| `ATEMIP.txt` | ATEM switcher IP (leave blank if no ATEM) |
| `Contact.txt` | Support contact message shown in Help |
| `password.enc` | Operator login password (set via app UI) |

Write each file to `/home/pi/hallptz/`:

```bash
echo "172.16.1.11" > /home/pi/hallptz/PTZ1IP.txt
echo "172.16.1.12" > /home/pi/hallptz/PTZ2IP.txt
# VISCA IDs are now set in config.yaml: cameras[0].visca_id and cameras[1].visca_id
```

---

## Phase 5 — Directory structure

After installation the following structure must exist:

```text
/home/pi/hallptz/           ← app code (git repo)
/home/pi/hallptz/logs/      ← runtime logs
/home/pi/hallptz_backups/   ← backup archives (created by rollback/backup scripts)
/etc/systemd/system/hallptz-control.service
```

Permissions:

```bash
sudo chown -R pi:pi /home/pi/hallptz /home/pi/hallptz_backups
```

---

## Phase 6 — First boot verification

```bash
# 1. Start the service
sudo systemctl start hallptz-control

# 2. Check status
sudo systemctl status hallptz-control

# 3. View logs
journalctl -u hallptz-control -n 50

# 4. Run unit tests (on the Pi — hardware-free)
cd /home/pi/hallptz
python -m pytest --tb=short -q
```

Confirm on screen:
- [ ] Splash screen appears and shows camera status within 15 seconds.
- [ ] No Python error on startup.
- [ ] Login screen accepts the operator password.
- [ ] Both camera cards visible on splash.

---

## What must NOT be in the golden image

- Customer passwords or `password.enc`
- Customer camera IPs or VISCA IDs
- Customer preset maps (`chairman_presets.json`, `seat_names.json`)
- Any private keys or certificates
- ATEM credentials

Apply all customer-specific data after cloning/flashing using Phase 4.

---

## Cloning an existing good image

To replicate a working installation to a new card:

1. On the source Pi: back up runtime data (`docs/UPDATE_ROLLBACK.md` — backup steps).
2. Clone the SD card using `dd` or Raspberry Pi Imager.
3. On the new card: **remove** customer-specific files from Phase 4.
4. On the new Pi: apply the correct customer config from Phase 4.
5. Run Phase 6 verification on the new Pi.

---

## Related documents

- `docs/INSTALL_RPI.md` — full end-to-end Raspberry Pi installation guide
- `docs/UPDATE_ROLLBACK.md` — update and rollback procedure
- `docs/RELEASE_CHECKLIST.md` — release gate checklist before customer deployments
- `docs/SOAK_TEST.md` — real-world soak test after deployment
- `runtime/installer/install.sh` — automated installer script
- `runtime/installer/rollback.sh` — safe rollback script
- `runtime/systemd/hallptz-control.service` — systemd service template
