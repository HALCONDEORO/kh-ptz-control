# Install KH PTZ Control: one-page checklist

For a **new installation**, use Raspberry Pi 4 or 5, Raspberry Pi OS Bookworm
64-bit **Desktop**, system Python 3.11 and an **X11 desktop session**. Bookworm
normally starts with Wayland: select X11 in `sudo raspi-config` > Advanced
Options > Wayland, then reboot. The Pi 4 Bullseye/Python 3.9.2 setup is a legacy
baseline, not the new-install target. See the [runtime matrix](docs/RPI_RUNTIME_BASELINE.md).

## Before changing a working installation

- Keep a copy of the installed application and configuration **off the Pi**.
  Do not assume the installer made one. Keep the working SD card or a verified
  recoverable image and record its version. A backup file is not a tested restore.
- Choose an exact reviewed tag or full commit SHA. Latest `main` is not an
  approved release. New stable releases require physical validation.
- Work outside a live meeting, with someone watching both cameras and a physical
  stopping fallback available. Do not run a second controller or discovery tool
  while the operator application is connected.

## Install from the Pi desktop

Run as the existing desktop user, not root. Read every result before continuing:

```bash
git clone https://github.com/HALCONDEORO/kh-ptz-control.git khptz
cd khptz
read -r -p "Approved tag or full commit SHA: " APPROVED_REVISION &&
git checkout --detach "$APPROVED_REVISION" &&
git rev-parse HEAD &&
bash install_khptz_rpi.sh --guide
```

Stop if checkout fails or the displayed SHA differs from the approved build.
Keep the same terminal open. Only after reviewing the guide:

```bash
sudo bash install_khptz_rpi.sh --wizard-user "$USER" --check
```

Only after readiness **PASS**:

```bash
sudo bash install_khptz_rpi.sh --wizard-user "$USER"
```

Do not add `--atem` or `--dev` on Bookworm: its system pip is externally managed.
Exit **20** means setup remains; exit **30** means stop and inspect the failure.
Follow installer instructions for reboot/login, then complete the wizard
(`khptz setup` from the desktop if requested). Set your own login passwords.
Do not paste passwords, camera addresses or room/member details into issues.

## Rehearse, then hand over

Check camera selection, CALL vs SET, saved framing, joystick release, STOP,
closing, reconnect and restart recovery on the actual equipment. USER can use
Help (`?` under Admin Mode) > STOP BOTH CAMERAS; ADMIN also has STOP ALL.
A green status or queued command is **not** proof that a camera moved or stopped.
Do not replace the working build until the equipment rehearsal is accepted.
For rollback, stop using the failed candidate and follow the
[full installation/backup/restore guide](docs/INSTALL_RPI.md) with your saved build
and configuration. Keep the physical fallback available throughout.

## No camera available? Try the separate rehearsal

From a disposable source checkout, Python 3.9+ is enough for this console-only
adapter exercise; it does not need PyQt, a Pi, passwords or camera addresses:

```bash
python3 -m simulation.rehearsal
python3 -m simulation.rehearsal --json
python3 -m unittest -q test_rehearsal
```

It exercises the existing in-memory `FakeCamera` adapter for Platform and
Comments: power on, save/recall preset 3, stop and standby. Socket operations are
denied in this command's process. It does not load production configuration or
write configuration, start discovery, change system services or launch the GUI.
Python may create ordinary `__pycache__` files in the checkout.

This is **not** the full operator screen or a simulation of real hardware
latency, VISCA transport, physical STOP or a Pi installation. Do not use the
legacy `adapters/sim_mode.py on` helper on a working installation: it rewrites
local camera configuration and is a different mechanism.

[Operator guide](docs/OPERATOR_GUIDE.md) | [Full install guide](docs/INSTALL_RPI.md)
