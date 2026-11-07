# Hardening 2: administrator store and preventive restore backup

Base reviewed: `75812b97500ef583c68af9e41f69fd80568557df`.

## Changes

- In the production layout, administrator credentials move from
  `/var/lib/khptz/admin.enc` to `/etc/khptz/secrets/admin.enc`.
  The parent is root:khptz 0750, outside all recursive data permission changes.
  Provisioning still writes the file 0600 and assigns it to the service account.
  The desktop GUI group cannot delete/replace it or read the machine-bound blob.
  Explicit nonproduction data overrides retain their isolated existing layout.
- Missing, unreadable or corrupt admin credentials deny administrator access.
  The operator password is never an implicit migration credential.
- The installed user GUI sets `KHPTZ_GUI_MODE=user`; ordinary administrator
  verification in that mode returns false without reading the credential.
  There is no permission relaxation to make local verification appear to work.
- Restore aborts before its first destination write when creating the preventive
  backup raises, returns no path or leaves no backup file. Dry-run is unchanged.
- Supercore is intentionally outside this patch. Its independent removal must
  land before claiming *all* administrator entry paths are disabled.

## Deployment gate: not executed by this patch

No installer, migration, host permissions, systemd action or real credential
has been applied during development. Review and explicit deployment approval
are required. There is no hardware validation.

Existing installations are deliberately not migrated on authentication. A blob
from a GUI-writable directory cannot be trusted as an administrator identity.
The installer refuses a legacy admin path before making installation changes.
Do not simply copy it or adopt password.enc as the new administrator secret.

For an approved maintenance window, with GUI/service stopped and installed code
reviewed, a privileged administrator must prepare the protected parent with
root:khptz ownership and 0750 mode, then run the installed command
`sudo python3 -m runtime.migrate_admin_secret` from the installed app directory.
It prompts privately for a new administrator password and confirmation, writes
0600, assigns the credential to khptz and removes only the legacy admin path.
It does not read/change the operator password. No password command-line option
exists. If setup or reset fails, leave access closed and investigate before
restarting. Validate ownership, directory chain, credential readability by the
service user, desktop-group denial and non-destructive login tests on the target
before approving release. Recovery/reinstall must preserve this directory.

## Known functional limits and next work

User-mode GUI administrator elevation is unavailable until a privileged
verification broker exists. Do not advertise it as ready. The broker needs an
explicit narrow IPC protocol, caller checks, retry/rate limits and privileged
password changes. It must not return plaintext credentials to the desktop.

The protected parent also prevents the service account from atomically replacing
admin.enc through the old in-GUI Change Admin Password action. Until a broker
lands, administer that credential with the privileged offline reset command,
not the in-GUI change action. The production in-GUI password-change button is disabled with a visible
notice, and its controller also refuses direct calls before requesting a
password. Explicit test/development data overrides retain the local flow. Operator password policy is unchanged.

This change is not a general rewrite of machine-bound credential encryption,
backup authenticity or multi-file rollback after a later restore write failure.
