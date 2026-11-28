#!/bin/bash
# KH PTZ Control: supervised hall update to reviewed source 69516d7.
# Local recovery copies remain on this SD. They do not protect against SD loss.
set -euo pipefail
FINAL_SHA=69516d7fd77d2c8b25f11c02fff21069192c5bf7

stop() { printf '\nSTOP: %s\nNo continúes ni repitas la instalación a ciegas.\n' "$*" >&2; exit 1; }
[[ "$FINAL_SHA" =~ ^[0-9a-f]{40}$ ]] || stop 'SHA no válido.'
[[ "$USER" != root ]] || stop 'Abre la terminal como usuario del escritorio.'
sudo -v
PHASE=preparation
on_exit() {
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
        if [[ "$PHASE" == preparation ]]; then
            printf '\nPreparación detenida. El instalador no se ha iniciado; no se ha parado el servicio.\n' >&2
        else
            printf '\nActualización o verificación detenida. Conserva la salida; no repitas ni restaures a ciegas.\n' >&2
        fi
    fi
}
trap on_exit EXIT
sudo test -f /etc/khptz/install-state.env || stop 'No encuentro el estado de instalación; hace falta revisar el arranque.'
[[ "$(sudo systemctl show khptz-control -p WorkingDirectory --value)" == /opt/khptz ]] || stop 'La ruta de arranque no es la instalación esperada.'
[[ "$(sudo systemctl show khptz-control -p User --value)" == khptz ]] || stop 'El usuario del servicio no coincide.'
sudo systemctl show khptz-control -p ExecStart --value | grep -Fq '/usr/bin/python3 /opt/khptz/main.py' || stop 'El comando real de arranque no coincide.'
sudo systemctl is-active --quiet khptz-control || stop 'El servicio debe estar activo antes de actualizar para conservar el reinicio automático.'
sudo test -f /etc/khptz/.provisioned || stop 'No consta instalación aprovisionada.'
if sudo test -e /var/lib/khptz/admin.enc || sudo test -L /var/lib/khptz/admin.enc; then
    stop 'Credencial admin antigua. Requiere mantenimiento protegido; no se ha actualizado.'
fi
sudo test -f /etc/khptz/secrets/admin.enc || stop 'No se ha podido verificar el almacén admin protegido.'
# Read only named state fields. Never execute install-state.env as shell code.
state() { sudo sed -n "s/^$1=//p" /etc/khptz/install-state.env | tr -d '"' | tail -n1; }
[[ "$(state KHPTZ_INSTALL_MODE)" == product ]] || stop 'La instalación no es de tipo product.'
[[ "$(state KHPTZ_GUI_MODE)" == system ]] || stop 'No se cambia de modo de arranque durante esta actualización.'
[[ "$(state KHPTZ_WIZARD_USER)" == "$USER" ]] || stop 'El usuario de escritorio no coincide con la instalación.'
OLD_REF="$(state KHPTZ_INSTALLED_REF)"
[[ -n "$OLD_REF" && "$OLD_REF" != unknown ]] || stop 'No consta revisión anterior recuperable.'
WORK="$(mktemp -d "$HOME/khptz-supervised-XXXXXX")"
REPO="$WORK/source"
git clone https://github.com/HALCONDEORO/kh-ptz-control.git "$REPO"
git -C "$REPO" checkout --detach "$FINAL_SHA"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$FINAL_SHA" ]] || stop 'La revisión descargada no coincide.'
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || stop 'La copia fuente tiene cambios.'
git -C "$REPO" rev-parse --verify --end-of-options "$OLD_REF^{commit}" >/dev/null || stop 'No se puede recuperar la revisión anterior.'
sudo bash "$REPO/install_khptz_rpi.sh" --wizard-user "$USER" --check
# No camera/network probes and no second GUI have been started above.
printf '\nTermina la sesión de cámara y deja de usar la aplicación durante la copia. No cierres el servicio.\n'
read -r -p 'Escribe PAUSA cuando nadie esté usando la aplicación: ' CONFIRM
[[ "$CONFIRM" == PAUSA ]] || stop 'Actualización cancelada antes de instalar.'
# Do not pre-stop the service: the official installer owns stop/restart.
# The installed backup command is deliberately run from /, not the candidate tree.
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ZIP="/var/backups/khptz/before_supervised_$STAMP.zip"
(cd / && sudo -u khptz env KHPTZ_CONFIG_DIR=/etc/khptz KHPTZ_DATA_DIR=/var/lib/khptz KHPTZ_LOG_DIR=/var/log/khptz KHPTZ_BACKUP_DIR=/var/backups/khptz PYTHONPATH=/opt/khptz /usr/bin/python3 -m runtime.cli backup --dest "$ZIP")
# Verify the official archive in the installed release and in the candidate.
(cd / && sudo env KHPTZ_CONFIG_DIR=/etc/khptz KHPTZ_DATA_DIR=/var/lib/khptz PYTHONPATH=/opt/khptz /usr/bin/python3 -m runtime.cli restore "$ZIP" --dry-run)
(cd / && sudo env KHPTZ_CONFIG_DIR=/etc/khptz KHPTZ_DATA_DIR=/var/lib/khptz PYTHONPATH="$REPO" /usr/bin/python3 -m runtime.cli restore "$ZIP" --dry-run)
DEST="$WORK/local-recovery-$STAMP"
sudo mkdir -m 700 -- "$DEST"
sudo cp -- "$ZIP" "$DEST/config-data.zip"
sudo cp -- /etc/khptz/install-state.env "$DEST/install-state.env"
sudo tar --exclude='*.enc' --exclude='*.key' --exclude='password.*' --exclude='admin.*' --exclude='config.yaml' --exclude='PTZ*IP.txt' --exclude='Contact.txt' -czf "$DEST/installed-code.tar.gz" -C /opt khptz
# A source bundle retains the actual previous revision without changing the checkout.
OLD_SHA="$(git -C "$REPO" rev-parse --verify --end-of-options "$OLD_REF^{commit}")"
git -C "$REPO" update-ref refs/heads/khptz-recovery-before-update "$OLD_SHA"
git -C "$REPO" bundle create "$WORK/previous-source.bundle" refs/heads/khptz-recovery-before-update
sudo cp -- "$WORK/previous-source.bundle" "$DEST/previous-source.bundle"
sudo cmp -- "$ZIP" "$DEST/config-data.zip"
sudo tar -tzf "$DEST/installed-code.tar.gz" | tail -n 3
sudo cmp -- /etc/khptz/install-state.env "$DEST/install-state.env"
sudo cmp -- "$WORK/previous-source.bundle" "$DEST/previous-source.bundle"
sync
git -C "$REPO" bundle verify "$WORK/previous-source.bundle"
sudo bash "$REPO/runtime/installer/rollback.sh" --source "$REPO" --to khptz-recovery-before-update --dry-run
# WORK is a private mktemp directory owned by the desktop user.
# Keep this redirection unprivileged; only reading the protected files needs sudo.
# shellcheck disable=SC2024
sudo sha256sum /etc/khptz/secrets/admin.enc /var/lib/khptz/password.enc > "$WORK/credential-digests-before.private"
printf '\nCopia local verificada en %s. No es una imagen completa de la SD.\n' "$DEST"
PHASE=installation
RC=0
sudo bash "$REPO/install_khptz_rpi.sh" --wizard-user "$USER" || RC=$?
printf '\nCódigo del instalador: %s\n' "$RC"
case "$RC" in
    0|10|20) ;;
    *) stop 'El instalador no terminó correctamente. Conserva la salida para revisar.' ;;
esac
# Confirm credentials were preserved, without showing their contents or hashes.
sudo sha256sum --check --status "$WORK/credential-digests-before.private" || stop 'La integridad de las credenciales ha cambiado; requiere revisión.'
sudo rm -- "$WORK/credential-digests-before.private"
sudo systemctl is-active --quiet khptz-control || stop 'El servicio no está activo tras actualizar.'
VERIFY_RC=0
sudo /usr/local/bin/khptz verify-install || VERIFY_RC=$?
printf '\nCódigo de verify-install: %s\n' "$VERIFY_RC"
printf '\nConserva esta carpeta fuente para volver atrás: %s\n' "$REPO"
printf 'Rollback de código (no lo ejecutes sin revisar el resultado):\n'
printf 'sudo bash %q --source %q --to %q --dry-run\n' "$REPO/runtime/installer/rollback.sh" "$REPO" khptz-recovery-before-update
[[ "$VERIFY_RC" == 0 ]] || stop 'La verificación requiere revisión; no dar la actualización por aceptada.'
[[ "$RC" != 20 ]] || stop 'El instalador indica preparación pendiente. No dar por lista para uso.'
PHASE=complete
printf '\nActualización instalada para ensayo supervisado. Comprueba pantalla, login, STOP y ambas cámaras. No es aceptación física ni versión estable.\n'

