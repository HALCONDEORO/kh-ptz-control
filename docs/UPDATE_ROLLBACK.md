# Update and Rollback Procedure

Safe procedure for updating and rolling back Hall PTZ Control on a customer Raspberry Pi.

> Paths below assume a **product install** (`install.sh` without `--dev`):
> code in `/opt/hallptz`, config in `/etc/hallptz`, runtime data in `/var/lib/hallptz`,
> logs in `/var/log/hallptz`, backups in `/var/backups/hallptz`, service user `hallptz`.
> See `docs/RUNTIME_PATH_CONTRACT.md` for the canonical layout. For a
> developer install (`install.sh --dev`), substitute `/home/<user>/hallptz` for
> the code path and your own user for `hallptz`.

---

## How a product install is laid out

`/opt/hallptz` is a **deployed artifact, not a git checkout**. `install.sh` copies
the tree there with `rsync --delete --exclude='.git'` and leaves it `root:hallptz`
mode 0750, so the service user cannot write it (`ProtectSystem=strict` in the
unit enforces the same thing at runtime).

The git checkout stays where the operator cloned it (e.g. `/home/<user>/hallptz`).
Updates and rollbacks are therefore **re-deploys from that checkout**, never a
`git checkout` inside `/opt/hallptz`.

`install.sh` records what it needs for this in `/etc/hallptz/install-state.env`:

| Key | Meaning |
|---|---|
| `HALLPTZ_INSTALLED_REF` | git ref currently deployed to `/opt/hallptz` |
| `HALLPTZ_PREVIOUS_REF` | ref the last update replaced — the default rollback target |
| `HALLPTZ_SOURCE_DIR` | the git checkout this install was deployed from |
| `HALLPTZ_WIZARD_USER` | desktop user owning the setup-wizard provisioning channel |
| `HALLPTZ_INSTALLED_VERSION` / `HALLPTZ_INSTALLED_AT` | audit fields |

It lives in `/etc/hallptz` (not `/opt/hallptz`) so it survives every re-deploy.

> **Provisioning is never touched.** `/etc/hallptz/config.yaml`,
> `/etc/hallptz/.provisioned` and both password secrets in `/var/lib/hallptz` sit
> outside the deploy target and `install.sh` never overwrites an existing
> `config.yaml`. An update or rollback does **not** re-run the setup wizard and
> does **not** ask for passwords again.

---

## Before any update

1. **Record current version.**

   ```bash
   cat /etc/hallptz/install-state.env
   ```

2. **Back up config and runtime data.**
   The installer and rollback scripts do this automatically via `hallptz backup`
   (manifest-based ZIP — see `docs/BACKUP_RESTORE_CONTRACT.md`). For a manual
   update:

   ```bash
   sudo -u hallptz python3 -m runtime.cli backup
   ```

   Config (`/etc/hallptz`) and runtime data (`/var/lib/hallptz`) live outside the
   code directory, so re-deploying code in step 4 never touches them — the
   backup here is a safety net, not a required restore step.

3. **Stop the service.**

   ```bash
   sudo systemctl stop hallptz-control
   ```

4. **Apply the update** from the source checkout. Only install tagged releases:

   ```bash
   cd /home/<user>/hallptz            # the git checkout, not /opt/hallptz
   git fetch --tags origin
   git checkout v3.x.y             # replace with target tag
   sudo bash runtime/installer/install.sh
   ```

   `install.sh` re-deploys the tree, re-applies ownership/modes, re-registers
   the systemd units, and rolls `HALLPTZ_INSTALLED_REF` into `HALLPTZ_PREVIOUS_REF`
   so the rollback target is set automatically.

5. **Start the service and verify.**

   ```bash
   sudo systemctl start hallptz-control
   hallptz verify-install
   journalctl -u hallptz-control -n 30
   ```

---

## Rollback

Use `runtime/installer/rollback.sh` to revert to the previous working version.

### Automatic rollback (recommended)

```bash
sudo bash /opt/hallptz/runtime/installer/rollback.sh
```

The script will:
- Read `/etc/hallptz/install-state.env` for the source checkout and the target ref
  (`HALLPTZ_PREVIOUS_REF`).
- Create a safety snapshot via `hallptz backup` before reverting (config/data
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
sudo bash /home/<user>/hallptz/runtime/installer/rollback.sh --dev
```

### Dry-run first (preview without changes)

```bash
sudo bash /opt/hallptz/runtime/installer/rollback.sh --dry-run
```

### Roll back to a specific tag or commit

```bash
sudo bash /opt/hallptz/runtime/installer/rollback.sh --to v3.1.0
```

### Roll back an install with no recorded state

An install made before `install-state.env` existed has nothing to read. Point
the script at the checkout and the ref explicitly:

```bash
sudo bash /opt/hallptz/runtime/installer/rollback.sh --source /home/<user>/hallptz --to v3.1.0
```

### Manual rollback (copy-paste safe)

If the script is unavailable:

```bash
# 1. Stop service
sudo systemctl stop hallptz-control

# 2. Safety snapshot (optional but recommended)
sudo -u hallptz python3 -m runtime.cli backup

# 3. Revert code in the SOURCE CHECKOUT (not /opt/hallptz — it has no .git)
cd /home/<user>/hallptz
TARGET="v3.1.0"
git fetch --tags origin
git checkout "$TARGET"

# 4. Re-deploy
sudo bash runtime/installer/install.sh

# 5. Restart service
sudo systemctl start hallptz-control
sudo systemctl status hallptz-control
journalctl -u hallptz-control -n 30

# 6. Confirm cameras connect and app is healthy
hallptz verify-install
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
