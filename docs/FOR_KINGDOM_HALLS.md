# KH PTZ Control for Kingdom Halls

KH PTZ Control is a free, open-source (MIT) touchscreen application that lets a
Kingdom Hall control its VISCA-over-IP PTZ cameras from a Raspberry Pi: the operator taps
a seat on a visual layout of the hall and the cameras frame that person, so friends
commenting from the audience can be seen on the hall's displays during the meeting.

It was built for a real hall and is used in live meetings. Any hall may use it freely.

---

## What you need

| Item | Notes |
|---|---|
| Raspberry Pi 4 (4 GB+) | Runs the operator touchscreen app 24/7. |
| 1080p touchscreen | The operator's console at the sound desk. |
| VISCA-over-IP PTZ cameras | One or two (platform / audience), TCP port 5678. |
| Wired network | Cameras and Pi on the same LAN, with static IPs. |
| microSD card (16 GB+) | Raspberry Pi OS (Bullseye baseline). |
| Optional: Blackmagic ATEM | For video mixing integration. |

## Install (one command)

On the Pi, with the repository checked out:

```bash
sudo bash install_khptz_rpi.sh --wizard-user <your-desktop-user>
```

The installer is idempotent (safe to re-run), sets up the service, the autostart and the
diagnostics, and ends by telling you the single next action. After it finishes, a graphical
setup wizard opens: no terminal needed. You enter the camera IPs, pick a profile
(one or two cameras) and lay out the seats. `khptz doctor` verifies the installation and
tells you in plain terms whether the appliance is ready, needs configuration, or has a
real fault.

Full details: [docs/INSTALL_RPI.md](INSTALL_RPI.md).

## Using it during the meeting

The operator guide covers the four safety actions (STOP, STOP ALL, Safety Reset and the
standby flow) in plain language: [docs/OPERATOR_GUIDE.md](OPERATOR_GUIDE.md).

New operators can practise without any camera connected: demo mode simulates the full
hall with fake cameras, so training never touches the real equipment.

## Privacy

The app can optionally store names of people on seats (so the operator sees who sits
where). Everything stays on the hall's own Pi; nothing is sent anywhere. Each hall decides
whether to use names at all - see [docs/PRIVACY_NOTES.md](PRIVACY_NOTES.md). Keeping the
Pi off the public internet is part of the supported setup.

## Project status and support

The software is functional and in its MVP hardening phase: it runs in production in its
home hall, and the install/validate flow is being hardened for other halls (see issue
#381 for the hardware validation gate). Check the open issues before installing, and
please report anything you find through GitHub Issues on the repository.

## Licence

MIT - use it, adapt it and share it freely. Copyright (c) 2026 MACD Adaptive Limited.
See [LICENSE](../LICENSE).
