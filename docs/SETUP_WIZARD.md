# On-device setup wizard

The setup wizard is the **on-device, touchscreen first-run experience** that runs
on the Raspberry Pi itself. It replaces console-based setup: an operator taps
through a few pre-filled screens and, when it finishes, the install is configured
and the service is running.

It is **not** a Windows tool and does not run off-device. Everything happens on
the Pi's own desktop session.

---

## Entry point

```bash
hallptz setup            # open the wizard (fresh install)
hallptz setup --force    # Repair: reopen on an already-provisioned install
```

`hallptz setup` is **idempotent**. Once the install is provisioned (the
`/etc/hallptz/.provisioned` marker exists) it prints a note and exits `0` **without**
opening a window. That is what lets the same command be wired to first-boot
autostart and fire harmlessly on every login after setup has completed once.

| Situation | `hallptz setup` | `hallptz setup --force` |
|---|---|---|
| Not provisioned (fresh) | Opens the wizard | Opens the wizard |
| Already provisioned | Exits 0, no window | Opens in **Repair** mode |

Source: [`runtime/cli.py`](../runtime/cli.py) (`cmd_setup`) →
[`runtime/setup_launcher.py`](../runtime/setup_launcher.py)
(`setup_wizard_needed` guard + `run_setup_wizard`).

---

## First-boot autostart

The product installer (`sudo ./runtime/installer/install.sh`, product mode)
installs two separate launchers so the wizard appears automatically on first
boot **and** the menu entry can still open Repair afterwards:

- `runtime/hallptz-setup-menu.desktop` (`Exec=hallptz setup --force`) →
  `/usr/share/applications/hallptz-setup.desktop` (applications menu), and
- `runtime/hallptz-setup.desktop` (`Exec=hallptz setup`, no `--force`) dropped into
  the desktop (wizard) user's `~/.config/autostart/hallptz-setup.desktop` (XDG
  autostart on login).

The autostart entry self-suppresses once provisioned — it fires on every login
but quietly does nothing after the first successful setup. The menu entry
always passes `--force`, so clicking it after setup reopens Repair rather than
doing nothing.

The desktop (wizard) user defaults to `$SUDO_USER`; override with
`--wizard-user <user>`.

---

## Repair mode

`hallptz setup --force` on a provisioned install opens the wizard **pre-filled with
the current configuration** (site, contact, cameras, ATEM, network profile), read
from the installed `config.yaml`. The operator edits values in place instead of
re-entering everything.

Passwords are **not** recoverable from the encrypted secrets, so they are left
blank and must be re-confirmed on the Passwords screen.

If `config.yaml` exists but fails to load, the wizard refuses to open at all
rather than proceeding with generic defaults that a save would silently write
over the real cameras/ATEM/network settings — `hallptz doctor` is the next step.

Source: `ProvisioningService.answers_from_settings` / `load_existing_answers`
in [`application/provisioning_service.py`](../application/provisioning_service.py).

### Admin sign-in gate

Reopening Repair on an already-provisioned install requires the **current
administrator password** first (an `AdminAuthPage` shown as the wizard's first
screen). Without it, desktop-session access to the wizard user alone would be
enough to reconfigure cameras/network or reset both passwords.

That page only *collects* the password — it does not verify it. The wizard
runs unprivileged in the desktop session and cannot reliably decrypt the
`hallptz:hallptz`-owned admin secret itself. Verification happens in the
**privileged** provisioning oneshot (`runtime/provision.py::run_provision`),
which checks it via `application.authentication.verify_admin` before applying
anything, whenever `.provisioned` already exists. This also closes the more
direct bypass: since `/run/hallptz` is writable by the wizard user, a raw request
dropped there — skipping the wizard UI entirely — would otherwise apply
without ever proving the admin password.

A wrong password surfaces as a failure on the Installing page (via the same
`issues` mechanism as any other validation failure), not immediately on the
sign-in screen.

---

## How provisioning actually happens (privilege split)

The wizard runs **unprivileged** in the desktop session — it never needs root and
never writes `/etc/hallptz` directly. Instead:

```text
wizard (desktop user)
  └─ writes request → /run/hallptz/request.json   (tmpfs, 0750 root:<wizard-user>)
       └─ hallptz-provision.path (systemd) reacts
            └─ runtime/provision.py (root oneshot):
                 validate → snapshot → apply config.yaml + secrets + OS steps
                 → write .provisioned marker → write result.json → shred request
```

The single `sudo` step is running the installer once; after that the wizard
provisions with **no further password prompt** via this channel.

- Request/result contract: [`application/provision_handoff.py`](../application/provision_handoff.py)
- Privileged entry point: [`runtime/provision.py`](../runtime/provision.py)
- Channel units: `runtime/systemd/hallptz-provision.{service,path}`

### Rollback safety

Before applying, the privileged step snapshots the files a re-provision
overwrites (`config.yaml` + both secrets). If apply fails mid-flow, it restores
the previous bytes (repair) or removes partial writes (fresh install), so a
failed run never leaves a half-written config. See `ConfigSnapshot` in
[`runtime/provision.py`](../runtime/provision.py).

---

## Screens

Welcome → Device check → Room details → Cameras → Optional (ATEM + network) →
Passwords (operator + administrator) → Review → Installing → Done.

- **Device check** gates Next while any preflight check is blocking.
- **Review** gates Finish while validation issues remain (nothing is written
  until confirmed).
- **Installing** drops the request and polls the result with a timer — the
  touchscreen stays responsive and Next stays disabled until provisioning
  succeeds.
- **Done** independently verifies the install (marker + config present) and
  points to `hallptz doctor` if verification fails.

Pages collect input only; all file writes go through `ProvisioningService`
(headless, Qt-free). Source: [`ui/setup_wizard/`](../ui/setup_wizard/). The
branded touchscreen look is applied once via `setup_wizard_qss()` in
[`ui/styles.py`](../ui/styles.py).

---

## Validation status

Software-complete and unit-tested offscreen. **Real Raspberry Pi hardware QA is
still required** (#381): confirm the autostart fires in the desktop session, the
`/run/hallptz` channel converges, permissions are correct on real hardware, and the
touchscreen render is legible with the installed fonts.
