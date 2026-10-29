#!/usr/bin/env bash
# rollback.sh — Revert a KH PTZ Control update to the previous release
#
# Usage:
#   sudo bash rollback.sh [--dev] [--user <user>] [--dir <install-dir>]
#                         [--source <checkout>] [--to <git-ref>] [--dry-run]
#
# Modes (mirrors install.sh):
#   (default)  Product install: khptz user, /opt/khptz + /etc/khptz + /var/lib/khptz
#              + /var/log/khptz + /var/backups/khptz.
#   --dev      Developer install: current user, /home/<user>/khptz +
#              /home/<user>/.config/khptz (matches install.sh --dev).
#
# How a product rollback works:
#   /opt/khptz is a deployed artifact, not a git checkout — install.sh rsyncs the
#   tree with --exclude='.git', and it is root:khptz 0750 so the service user
#   cannot write it. Rolling back is therefore a *re-deploy*: check the source
#   checkout out at the previous ref and run install.sh again from there.
#   install.sh is idempotent and never touches an existing config.yaml, so the
#   setup wizard's provisioning (/etc/khptz/.provisioned, both password secrets,
#   camera settings) survives a rollback untouched — the wizard does not re-run.
#
#   The source checkout, the live ref and the previous ref are recorded by
#   install.sh in /etc/khptz/install-state.env.
#
# Safety rules:
#   - Config and runtime data live outside the install directory (see
#     docs/RUNTIME_PATH_CONTRACT.md), so re-deploying code never touches them.
#   - A safety snapshot is still taken before reverting, via `khptz backup`
#     (BackupService) — the same manifest-based backup used everywhere else,
#     not a hand-rolled file list.
#   - Stops the service cleanly before changing code.
#   - Prints self-test instructions after rollback.
#   - Dry-run mode available: set DRY_RUN=1 or pass --dry-run to preview
#     actions without executing.

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────

DEV_MODE=false
DRY_RUN="${DRY_RUN:-0}"
TARGET_REF=""
APP_USER_OVERRIDE=""
INSTALL_DIR_OVERRIDE=""
SOURCE_DIR_OVERRIDE=""

SERVICE_NAME="khptz-control"

# ── Argument parsing ──────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev)     DEV_MODE=true;              shift ;;
        --user)    APP_USER_OVERRIDE="$2";     shift 2 ;;
        --dir)     INSTALL_DIR_OVERRIDE="$2";  shift 2 ;;
        --source)  SOURCE_DIR_OVERRIDE="$2";   shift 2 ;;
        --to)      TARGET_REF="$2";            shift 2 ;;
        --dry-run) DRY_RUN=1;                  shift ;;
        --help)
            echo "Usage: sudo bash rollback.sh [--dev] [--user <user>] [--dir <install-dir>] [--source <checkout>] [--to <git-ref>] [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --dev     Developer layout (current user, /home/<user>/khptz) — matches install.sh --dev"
            echo "  --user    Override the app/service user"
            echo "  --dir     Override the install directory"
            echo "  --source  Override the source checkout to re-deploy from (product mode)"
            echo "  --to      Git tag or commit to roll back to (default: reads install-state.env)"
            echo "  --dry-run Print actions without executing them"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

# ── Resolve paths (mirrors install.sh layout) ─────────────────────────────────

if [[ "${DEV_MODE}" == "true" ]]; then
    APP_USER="${APP_USER_OVERRIDE:-${SUDO_USER:-${USER}}}"
    INSTALL_DIR="${INSTALL_DIR_OVERRIDE:-/home/${APP_USER}/khptz}"
    CONFIG_DIR="${INSTALL_DIR}"
    DATA_DIR="/home/${APP_USER}/.config/khptz"
    LOG_DIR="/var/log/khptz"
    BACKUP_DIR="/var/backups/khptz"
else
    APP_USER="${APP_USER_OVERRIDE:-khptz}"
    INSTALL_DIR="${INSTALL_DIR_OVERRIDE:-/opt/khptz}"
    CONFIG_DIR="/etc/khptz"
    DATA_DIR="/var/lib/khptz"
    LOG_DIR="/var/log/khptz"
    BACKUP_DIR="/var/backups/khptz"
fi

STATE_FILE="${CONFIG_DIR}/install-state.env"

# ── Helpers ───────────────────────────────────────────────────────────────────

log()  { echo "[rollback] $*"; }
run()  {
    if [[ "$DRY_RUN" == "1" ]]; then
        printf '[DRY-RUN] '
        printf '%q ' "$@"
        printf '\n'
    else
        "$@"
    fi
}
fail() { echo "[rollback] ERROR: $*" >&2; exit 1; }

# git bajo root tiene dos problemas: se niega a leer un repo de otro usuario
# ("dubious ownership") y, peor, fetch/checkout escriben .git/objects e index
# como root — el operador dueño del checkout ya no puede usar git después.
# Como root, git corre como el PROPIETARIO del checkout; el fallback con
# safe.directory solo aplica cuando el propietario es root o no se resuelve.
git_src() {
    if [[ "$(id -u)" -eq 0 ]]; then
        local owner
        owner="$(stat -c %U "$SOURCE_DIR" 2>/dev/null || echo root)"
        if [[ -n "$owner" && "$owner" != "root" ]]; then
            sudo -u "$owner" git -C "$SOURCE_DIR" "$@"
            return
        fi
    fi
    git -c safe.directory='*' -C "$SOURCE_DIR" "$@"
}

state_value() {
    # Read one KEY=value from install-state.env without sourcing it as shell.
    # The trailing `|| true` matters: `set -o pipefail` makes the whole pipeline
    # inherit sed's exit 2 when the state file is absent, which would abort the
    # script with no message at all from inside a "$(...)" assignment.
    sed -n "s/^$1=//p" "$STATE_FILE" 2>/dev/null | tr -d '"' | tail -n1 || true
}

sanitize_ref() {
    # Git refs may contain '/' (e.g. `--to release/v3.2.0`). Interpolated raw
    # into the backup filename that becomes a path separator, so `khptz backup
    # --dest` would write into a directory that does not exist and step 1 would
    # abort the rollback before it started.
    printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'
}

# ── Preflight checks ──────────────────────────────────────────────────────────

[[ "$(id -u)" -eq 0 ]] || fail "Run with sudo."
[[ -d "$INSTALL_DIR" ]] || fail "Install directory not found: $INSTALL_DIR (pass --dir or --dev if this is a developer install)"

WIZARD_USER=""
# Which launcher owns the GUI (#885). Recorded by install.sh; a rollback must
# re-deploy in the SAME mode, or reverting would silently move the GUI back to
# the system service and leave the desktop session launcher behind.
GUI_MODE=""

if [[ "${DEV_MODE}" == "true" ]]; then
    # Dev installs run straight from the checkout, so reverting in place is
    # both possible and the expected workflow.
    SOURCE_DIR="${SOURCE_DIR_OVERRIDE:-$INSTALL_DIR}"
    [[ -d "$SOURCE_DIR/.git" ]] || fail "Not a git repository: $SOURCE_DIR"
else
    SOURCE_DIR="${SOURCE_DIR_OVERRIDE:-}"
    if [[ -z "$SOURCE_DIR" ]]; then
        [[ -f "$STATE_FILE" ]] || fail \
            "No install state at $STATE_FILE — this install predates rollback support. Re-run install.sh from the source checkout first, or pass --source <checkout> --to <ref>."
        SOURCE_DIR="$(state_value KHPTZ_SOURCE_DIR)"
        WIZARD_USER="$(state_value KHPTZ_WIZARD_USER)"
        GUI_MODE="$(state_value KHPTZ_GUI_MODE)"
    fi
    [[ -n "$SOURCE_DIR" ]] || fail "Source checkout unknown — pass --source <checkout>."
    [[ -d "$SOURCE_DIR/.git" ]] || fail \
        "Source checkout is not a git repository: $SOURCE_DIR (pass --source <checkout>). /opt/khptz is a deployed copy with no .git — a rollback re-deploys from the checkout it was installed from."
    [[ -f "$SOURCE_DIR/runtime/installer/install.sh" ]] || fail \
        "install.sh not found in source checkout: $SOURCE_DIR"
fi

log "Mode            : $([[ ${DEV_MODE} == true ]] && echo 'developer' || echo 'product')"
log "App user        : $APP_USER"
log "Install dir     : $INSTALL_DIR"
log "Source checkout : $SOURCE_DIR"
log "Config dir      : $CONFIG_DIR"
log "Data dir        : $DATA_DIR"
log "Backup dir      : $BACKUP_DIR"

# ── Determine rollback target ─────────────────────────────────────────────────

if [[ -z "$TARGET_REF" ]]; then
    if [[ "${DEV_MODE}" == "false" && -f "$STATE_FILE" ]]; then
        TARGET_REF="$(state_value KHPTZ_PREVIOUS_REF)"
        [[ -n "$TARGET_REF" ]] && log "Rolling back to: $TARGET_REF (from install-state.env)"
    fi
    if [[ -z "$TARGET_REF" ]]; then
        PREV_FILE="$INSTALL_DIR/PREVIOUS_VERSION"
        if [[ -f "$PREV_FILE" ]]; then
            TARGET_REF="$(tr -d '[:space:]' < "$PREV_FILE")"
            log "Rolling back to: $TARGET_REF (from PREVIOUS_VERSION)"
        else
            # Fall back to the previous git tag in the source checkout
            TARGET_REF="$(git_src describe --tags --abbrev=0 HEAD^ 2>/dev/null || true)"
            [[ -n "$TARGET_REF" ]] || fail "Cannot determine rollback target. Use --to <git-ref>."
            log "Rolling back to previous tag: $TARGET_REF"
        fi
    fi
fi

if [[ "${DEV_MODE}" == "false" && -f "$STATE_FILE" ]]; then
    CURRENT_REF="$(state_value KHPTZ_INSTALLED_REF)"
fi
CURRENT_REF="${CURRENT_REF:-$(git_src describe --tags --always HEAD 2>/dev/null || echo unknown)}"

log "Current version : $CURRENT_REF"
log "Rollback target : $TARGET_REF"

[[ "$CURRENT_REF" != "$TARGET_REF" ]] || fail \
    "Rollback target is the version already installed ($CURRENT_REF) — nothing to do. Use --to <ref> to pick a different one."

if [[ "$DRY_RUN" == "1" ]]; then
    log "DRY-RUN mode — no changes will be made."
fi

# ── Step 1: Pre-rollback safety snapshot ──────────────────────────────────────
#
# Config (CONFIG_DIR) and runtime data (DATA_DIR) live outside INSTALL_DIR
# (see docs/RUNTIME_PATH_CONTRACT.md), so the code re-deploy in Step 3 cannot
# touch them. This snapshot is a safety net taken via the same manifest-based
# BackupService every other backup uses — not a separate ad hoc file list.

BACKUP_NAME="pre_rollback_$(sanitize_ref "${CURRENT_REF}")_$(date +%Y%m%d_%H%M%S).zip"
BACKUP_DEST="${BACKUP_DIR}/${BACKUP_NAME}"

log "Step 1: Creating pre-rollback backup → $BACKUP_DEST"
# Los KHPTZ_* van DESPUÉS de sudo: con env_reset, `env VAR=... sudo` entrega
# las variables a sudo, no al proceso privilegiado. PYTHONPATH fija el árbol
# desplegado: sin él, `python3 -m runtime.cli` depende del cwd del operador.
run sudo -u "$APP_USER" \
    KHPTZ_CONFIG_DIR="$CONFIG_DIR" KHPTZ_DATA_DIR="$DATA_DIR" \
    KHPTZ_LOG_DIR="$LOG_DIR" KHPTZ_BACKUP_DIR="$BACKUP_DIR" \
    PYTHONPATH="$INSTALL_DIR" \
    python3 -m runtime.cli backup --dest "$BACKUP_DEST"

log "Backup complete: $BACKUP_DEST"

# ── Step 2: Stop service ──────────────────────────────────────────────────────

log "Step 2: Stopping $SERVICE_NAME service"
SERVICE_STOPPED=0
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    run systemctl stop "$SERVICE_NAME"
    SERVICE_STOPPED=1
    log "Service stopped."
else
    log "Service was not running — skipping stop."
fi

# Si el rollback falla DESPUÉS de parar el servicio, cualquier salida anómala
# INTENTA rearrancarlo (disponibilidad, no garantía de árbol íntegro: el
# re-deploy pudo quedar a medias). Un rollback completado desarma el trap.
_restart_service_on_abort() {
    local rc=$?
    [[ "$SERVICE_STOPPED" == "1" ]] || return "$rc"
    [[ "${DRY_RUN}" == "1" ]] && return "$rc"
    echo "[rollback] ERROR (exit $rc) — restarting $SERVICE_NAME with the version still deployed" >&2
    systemctl start "$SERVICE_NAME" 2>/dev/null || true
    return "$rc"
}
trap _restart_service_on_abort EXIT

# ── Step 3: Revert code ───────────────────────────────────────────────────────

log "Step 3: Checking out $TARGET_REF in $SOURCE_DIR"
run git_src fetch --tags origin
run git_src checkout "$TARGET_REF"

if [[ "${DEV_MODE}" == "false" ]]; then
    # Re-deploy from the reverted checkout. install.sh mirrors the tree into
    # /opt/khptz (rsync --delete), re-applies ownership/modes and re-registers
    # the systemd units, and leaves /etc/khptz + /var/lib/khptz — including the
    # wizard's .provisioned marker and both password secrets — untouched.
    # It also rewrites install-state.env, so the ref we are leaving becomes the
    # rollback target for a future run.
    log "Step 3b: Re-deploying $TARGET_REF to $INSTALL_DIR via install.sh"
    # Preserve the recorded GUI mode across the re-deploy. Older state files
    # predate KHPTZ_GUI_MODE; install.sh's own default (system) then applies,
    # which matches how those installs were made.
    # Normalise the recorded mode rather than forwarding it blindly. install.sh
    # rejects an unknown --gui-mode with exit 1, so a single corrupt byte in
    # install-state.env — a truncated write, a hand edit — would abort the
    # rollback itself. This is the recovery path: it must survive damaged
    # metadata, not be stopped by it. Unknown resolves to the same safe default
    # every other component uses. Validated inline on purpose: recovery should
    # not depend on sourcing another file that may also be missing.
    case "$GUI_MODE" in
        user|system) ;;
        "")          ;;   # predates the flag; install.sh defaults to system
        *)
            log "WARNING: unrecognised KHPTZ_GUI_MODE '$GUI_MODE' in $STATE_FILE — using 'system'"
            GUI_MODE="system"
            ;;
    esac

    REDEPLOY_ARGS=()
    [[ -n "$WIZARD_USER" ]] && REDEPLOY_ARGS+=(--wizard-user "$WIZARD_USER")
    # El install.sh del TARGET es el que corre aquí: un target anterior al
    # flag --gui-mode rechazaría el argumento y abortaría la recuperación.
    if [[ -n "$GUI_MODE" ]]; then
        if grep -q -- '--gui-mode' "$SOURCE_DIR/runtime/installer/install.sh" 2>/dev/null; then
            REDEPLOY_ARGS+=(--gui-mode "$GUI_MODE")
        else
            log "WARNING: target install.sh does not support --gui-mode — deploying with its own default"
        fi
    fi
    run bash "$SOURCE_DIR/runtime/installer/install.sh" ${REDEPLOY_ARGS[@]+"${REDEPLOY_ARGS[@]}"}
else
    # Dev installs run from the checkout itself — nothing to re-deploy. Keep
    # PREVIOUS_VERSION as the dev-mode record of where to roll back next.
    log "Step 3b: Recording previous version for future rollback (was $CURRENT_REF)"
    if [[ "$DRY_RUN" == "1" ]]; then
        log "DRY-RUN: would write $CURRENT_REF to $INSTALL_DIR/PREVIOUS_VERSION"
    else
        printf '%s\n' "$CURRENT_REF" > "$INSTALL_DIR/PREVIOUS_VERSION"
    fi
fi

NEW_CURRENT="$(git_src describe --tags --always HEAD 2>/dev/null || echo "$TARGET_REF")"

# ── Step 4: Restart service ───────────────────────────────────────────────────
#
# install.sh only enables the unit, it never starts it; and khptz-control.service
# gates on ConditionPathExists=/etc/khptz/.provisioned. On a provisioned install
# that marker still exists (rollback never removes it), so this start succeeds.
# On an install that was never provisioned, systemd skips the unit — expected,
# and the setup wizard is still the way to finish setup.

if [[ "$GUI_MODE" == "user" ]]; then
    # La GUI corre como aplicación del usuario de escritorio: no hay servicio
    # de sistema que arrancar y forzarlo fallaría o duplicaría la instancia.
    log "Step 4: GUI runs as the desktop user — skipping system service start"
    SERVICE_STOPPED=0   # nada que rearrancar si algo falla después
else
    log "Step 4: Starting $SERVICE_NAME service"
    run systemctl start "$SERVICE_NAME"
    run sleep 3
fi

if [[ "$DRY_RUN" != "1" && "$GUI_MODE" != "user" ]]; then
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log "Service started successfully."
    elif [[ ! -f "${CONFIG_DIR}/.provisioned" && "${DEV_MODE}" == "false" ]]; then
        log "Service not running: this install has not been provisioned yet."
        log "Run the setup wizard (KHPTZ Setup in the applications menu) to finish setup."
    else
        log "WARNING: Service did not start. Check: journalctl -u $SERVICE_NAME -n 50"
    fi
fi

# Rollback completado: el trap de aborto no debe rearrancar nada en la salida.
SERVICE_STOPPED=0

# ── Step 5: Self-test instructions ────────────────────────────────────────────

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Rollback complete: $CURRENT_REF → $NEW_CURRENT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Verify the rollback:"
echo ""
echo "  1. Check service status:"
echo "     systemctl status $SERVICE_NAME"
echo ""
echo "  2. Post-install self-check:"
echo "     khptz verify-install"
echo "     khptz doctor"
echo ""
echo "  3. View recent logs:"
echo "     journalctl -u $SERVICE_NAME -n 50"
echo ""
echo "  4. Confirm the app launches and cameras connect."
echo ""
echo "Pre-rollback backup saved to: $BACKUP_DEST"
echo ""
