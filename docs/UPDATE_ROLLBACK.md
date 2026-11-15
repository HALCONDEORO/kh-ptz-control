# Update and Rollback Procedure

Safe procedure for updating and rolling back KH PTZ Control on a customer Raspberry Pi.

> Paths below assume a **product install** (`install.sh` without `--dev`):
> code in `/opt/khptz`, config in `/etc/khptz`, runtime data in `/var/lib/khptz`,
> logs in `/var/log/khptz`, backups in `/var/backups/khptz`, service user `khptz`.
> See `docs/RUNTIME_PATH_CONTRACT.md` for the canonical layout. For a
> developer install (`install.sh --dev`), substitute `/home/<user>/khptz` for
> the code path and your own user for `khptz`.

---

## How a product install is laid out

`/opt/khptz` is a **deployed artifact, not a git checkout**. `install.sh` copies
the tree there with `rsync --delete --exclude='.git'` and leaves it `root:khptz`
mode 0750, so the service user cannot write it (`ProtectSystem=strict` in the
unit enforces the same thing at runtime).

The git checkout stays where the operator cloned it (e.g. `/home/<user>/khptz`).
Updates and rollbacks are therefore **re-deploys from that checkout**, never a
`git checkout` inside `/opt/khptz`.

`install.sh` records what it needs for this in `/etc/khptz/install-state.env`:

| Key | Meaning |
|---|---|
| `KHPTZ_INSTALLED_REF` | git ref currently deployed to `/opt/khptz` |
| `KHPTZ_PREVIOUS_REF` | ref the last update replaced — the default rollback target |
| `KHPTZ_SOURCE_DIR` | the git checkout this install was deployed from |
| `KHPTZ_WIZARD_USER` | desktop user owning the setup-wizard provisioning channel |
| `KHPTZ_INSTALLED_VERSION` / `KHPTZ_INSTALLED_AT` | audit fields |

It lives in `/etc/khptz` (not `/opt/khptz`) so it survives every re-deploy.

> **Provisioning is never touched.** `/etc/khptz/config.yaml`,
> `/etc/khptz/.provisioned` and both password secrets in `/var/lib/khptz` sit
> outside the deploy target and `install.sh` never overwrites an existing
> `config.yaml`. An update or rollback does **not** re-run the setup wizard and
> does **not** ask for passwords again.

---

## Before any update

1. **Record current version.**

   ```bash
   cat /etc/khptz/install-state.env
   ```

2. **Back up config and runtime data.**
   `runtime/installer/install.sh` creates a pre-update backup automatically
   before it replaces the deployed tree: when an existing product install is
   found (`install-state.env` present), it runs the same manifest-based
   `khptz backup` the rollback script uses and aborts the update if the backup
   fails — before any GUI is stopped or the deployed tree is replaced
   (earlier setup/dependency steps may already have run). The archive is
   named `pre_update_<ref>_<timestamp>.zip` in `/var/backups/khptz`. The only
   way past the guard is the explicit `--skip-pre-update-backup` flag.

   Like every `khptz backup` archive, this is a **config/data manifest** —
   not the code, not the secrets, not an atomic device snapshot. Restoring
   means re-deploying the recorded ref (see Rollback below) and restoring the
   archive on top; it is not a self-contained image of the previous install.

   The automatic backup stays on the Pi, so still copy the resulting
   manifest-based ZIP off the Pi and verify the copy before installing. See
   `docs/BACKUP_RESTORE_CONTRACT.md` for the current archive contract. Older
   installed versions can have a different file set: verify that version's
   backup rather than assuming it includes today's runtime overrides.

   A data ZIP is not an SD-card image or a backup of credentials and installed
   code. Preserve the known-good source revision and installation state too;
   take a separate device image when full-device recovery is required. Keep
   backups private, not in public issues.

   Config (`/etc/khptz`) and runtime data (`/var/lib/khptz`) live outside the
   code directory. A code rollback leaves those current data files in place;
   it does not undo data-format changes or establish that older code can read
   them. Check compatibility before choosing a rollback target. Do not restore
   an old layout or reset provisioning merely to undo a code update.

3. **Stop the service.**

   ```bash
   sudo systemctl stop khptz-control
   ```

4. **Apply the update** from the source checkout. Only install tagged releases:

   ```bash
   cd /home/<user>/khptz            # the git checkout, not /opt/khptz
   git fetch --tags origin
   git checkout v3.x.y             # replace with target tag
   sudo bash runtime/installer/install.sh
   ```

   `install.sh` re-deploys the tree, re-applies ownership/modes, re-registers
   the systemd units, and rolls `KHPTZ_INSTALLED_REF` into `KHPTZ_PREVIOUS_REF`
   so the rollback target is set automatically.

5. **Start the service and verify.**

   ```bash
   sudo systemctl start khptz-control
   khptz verify-install
   journalctl -u khptz-control -n 30
   ```

---

## Rollback

Use `runtime/installer/rollback.sh` to revert to the previous working version.

### Automatic rollback (recommended)

```bash
sudo bash /opt/khptz/runtime/installer/rollback.sh
```

The script will:
- Read `/etc/khptz/install-state.env` for the source checkout and the target ref
  (`KHPTZ_PREVIOUS_REF`).
- Create a safety snapshot via `khptz backup` before reverting (config/data
  live outside the code directory, so they are never touched by the revert).
- Stop the service cleanly.
- Check the source checkout out at the target ref and **re-deploy it via
  `install.sh`** (preserving `--wizard-user`, so the provisioning channel and
  the setup-wizard autostart stay wired).
- Restart the service.
- Print self-test instructions.

It refuses to run if the target ref equals the version already installed, and
tells you what to do if the install predates `install-state.env`.

For a developer install, pass `--dev` (mirrors `install.sh --dev`):

```bash
sudo bash /home/<user>/khptz/runtime/installer/rollback.sh --dev
```

### Dry-run first (preview without changes)

```bash
sudo bash /opt/khptz/runtime/installer/rollback.sh --dry-run
```

### Roll back to a specific tag or commit

```bash
sudo bash /opt/khptz/runtime/installer/rollback.sh --to v3.1.0
```

### Roll back an install with no recorded state

An install made before `install-state.env` existed has nothing to read. Point
the script at the checkout and the ref explicitly:

```bash
sudo bash /opt/khptz/runtime/installer/rollback.sh --source /home/<user>/khptz --to v3.1.0
```

### Manual rollback (copy-paste safe)

If the script is unavailable:

```bash
# 1. Stop service
sudo systemctl stop khptz-control

# 2. Safety snapshot (optional but recommended)
sudo -u khptz python3 -m runtime.cli backup

# 3. Revert code in the SOURCE CHECKOUT (not /opt/khptz — it has no .git)
cd /home/<user>/khptz
TARGET="v3.1.0"
git fetch --tags origin
git checkout "$TARGET"

# 4. Re-deploy
sudo bash runtime/installer/install.sh

# 5. Restart service
sudo systemctl start khptz-control
sudo systemctl status khptz-control
journalctl -u khptz-control -n 30

# 6. Confirm cameras connect and app is healthy
khptz verify-install
```

---

## Uninstalling

Two levels: **remove the code only** (customer data stays, a later reinstall
picks it back up) or **full removal**. There is no uninstaller script; both
are manual. Take a backup first (`khptz backup`) and copy it off the
appliance if the presets, seat names or config matter later.

### 1. Stop everything first

```bash
# System services and the display-ready chain (system GUI mode)
sudo systemctl stop khptz-control.service khptz-provision.path \
                    khptz-provision.service khptz-display-ready.path \
                    khptz-display-ready.service
sudo systemctl disable khptz-control.service khptz-provision.path \
                       khptz-display-ready.path
```

If the install used `--gui-mode user`, stop the session-owned GUI as the
desktop user BEFORE removing its unit file, and reload the user manager:

```bash
# Run as the desktop user
systemctl --user stop khptz-gui.service
systemctl --user disable khptz-gui.service
systemctl --user daemon-reload
```

### 2. Remove the code only (keeps customer data)

```bash
sudo rm -rf /opt/khptz
```

Config and install state (`/etc/khptz`), presets and secrets
(`/var/lib/khptz`), logs (`/var/log/khptz`) and backups
(`/var/backups/khptz`) stay in place; reinstalling later resumes where the
install left off. Stop here for this variant.

Note: with `/opt/khptz` gone, the desktop autostart entries and the
`/usr/local/bin/khptz` launcher still point at the missing tree. The
session GUI unit has no `[Install]` section, but its autostart entry
starts it anyway, so the desktop session can log start-up errors until
the app is reinstalled - or until the entries from step 3 are removed.

### 3. Full removal (also deletes customer data)

Continuing from step 2:

```bash
# a. Unit files, the service drop-in and the tmpfiles entry
sudo rm -f /etc/systemd/system/khptz-control.service \
           /etc/systemd/system/khptz-provision.service \
           /etc/systemd/system/khptz-provision.path \
           /etc/systemd/system/khptz-display-ready.service \
           /etc/systemd/system/khptz-display-ready.path \
           /etc/systemd/user/khptz-gui.service \
           /etc/tmpfiles.d/khptz.conf
sudo rm -rf /etc/systemd/system/khptz-control.service.d
sudo systemctl daemon-reload

# If the session-owned GUI existed, reload the user manager too
# (as the desktop user) so it forgets the deleted unit:
systemctl --user daemon-reload

# b. Launchers, display helper and desktop entries
sudo rm -f /usr/local/bin/khptz \
           /usr/local/libexec/khptz-gui-session \
           /usr/local/libexec/khptz-display-session \
           /usr/share/applications/khptz-setup.desktop

# c. Autostart entries (run as the desktop user; the last two come from
#    repair_rpi_runtime.sh, current and legacy)
rm -f ~/.config/autostart/khptz-setup.desktop \
      ~/.config/autostart/khptz-gui.desktop \
      ~/.config/autostart/khptz-display-session.desktop \
      ~/.config/autostart/khptz-display-permission.desktop

# d. Config, data, logs and backups - this deletes the admin secrets and
#    every local backup
sudo rm -rf /etc/khptz /var/lib/khptz /var/log/khptz /var/backups/khptz

# e. Drop the scoped display grant (from the desktop session)
xhost -SI:localuser:khptz

# f. Last: remove the service user, once nothing on disk belongs to it
sudo userdel khptz
```

A `--dev` install writes the same system service file and
`/usr/local/bin/khptz`, and keeps the app and `config.yaml` inside the
checkout - but its data, logs and backups still live outside it
(`~/.config/khptz`, `/var/log/khptz`, `/var/backups/khptz`). Remove the
unit, the launcher, the checkout and those three directories; there is no
`khptz` service user in dev mode, so skip step f.

---

## Safety rules

- **Never overwrite customer data** (presets, seat names, schedules, camera config).
- **Only install from tagged releases** — not arbitrary commits unless marked as emergency hotfix.
- **Always stop the service** before changing code.
- **Backups are automatic.** The installer backs up before replacing an
  existing install; the rollback script backs up before reverting. Still keep
  an off-device copy of the most recent backup.
- **Run preflight/self-test** after update/rollback — see `docs/RELEASE_CHECKLIST.md`.

---

## Related documents

- `docs/RELEASE_CHECKLIST.md` — release gate checklist
- `docs/RUNTIME_PATH_CONTRACT.md` — canonical path/ownership layout
- `docs/BACKUP_RESTORE_CONTRACT.md` — backup/restore manifest contract
- `docs/SOAK_TEST.md` — real-world soak test after deployment
- `runtime/installer/rollback.sh` — rollback script
- `runtime/installer/install.sh` — install script
