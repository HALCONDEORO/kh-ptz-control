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
   The installer and rollback scripts do this automatically via `khptz backup`
   (manifest-based ZIP — see `docs/BACKUP_RESTORE_CONTRACT.md`). For a manual
   update:

   ```bash
   sudo -u khptz python3 -m runtime.cli backup
   ```

   Config (`/etc/khptz`) and runtime data (`/var/lib/khptz`) live outside the
   code directory, so re-deploying code in step 4 never touches them — the
   backup here is a safety net, not a required restore step.

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

## Safety rules

- **Never overwrite customer data** (presets, seat names, schedules, camera config).
- **Only install from tagged releases** — not arbitrary commits unless marked as emergency hotfix.
- **Always stop the service** before changing code.
- **Always take a safety backup** before updating or rolling back.
- **Run preflight/self-test** after update/rollback — see `docs/RELEASE_CHECKLIST.md`.

---

## Related documents

- `docs/RELEASE_CHECKLIST.md` — release gate checklist
- `docs/RUNTIME_PATH_CONTRACT.md` — canonical path/ownership layout
- `docs/BACKUP_RESTORE_CONTRACT.md` — backup/restore manifest contract
- `docs/SOAK_TEST.md` — real-world soak test after deployment
- `runtime/installer/rollback.sh` — rollback script
- `runtime/installer/install.sh` — install script
