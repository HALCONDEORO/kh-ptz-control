# Security Notes

These notes are practical security guidance for development, Raspberry Pi deployment and support work.

For incident handling, use [Security incident response](SECURITY_INCIDENT_RESPONSE.md).
For Raspberry Pi appliance hardening, use [Raspberry Pi security baseline](RPI_SECURITY_BASELINE.md).
For cameras, ATEM, switches and routers, use [AV device hardening checklist](AV_DEVICE_HARDENING_CHECKLIST.md).

## Repository Hygiene

Never commit real customer or local security files:

- `password.enc`
- `password.txt`
- `.env` or `.env.*`
- raw logs
- backup ZIP files
- private keys, signing keys or tokens
- real customer configuration or private network details

Use `config.example/` for safe examples only. Example values must be fake or generic and must not identify a real customer site.

## Passwords

Set or verify the customer admin password before any customer or pilot use.

Known risk to keep visible during support: older login/password paths may behave differently when `password.enc` is missing or corrupt. Treat a missing or corrupt password file as a support/security condition, not as a normal state.

Do not log raw passwords or attempted passwords. Do not paste password files into issues, support chats or email.

## Backups and Support Data

Backups and support artifacts can contain customer data. Before sharing them:

- confirm customer permission;
- remove password files, tokens and private keys;
- check logs for personal data and private network details;
- prefer sanitised summaries where possible.

Support bundles must not include secrets by default. If a bundle export is not yet implemented or verified, collect support data manually and check every file before sending it.

## Remote Support

Remote support should happen only with customer permission and a clear support purpose.

Do not change camera IPs, Raspberry Pi network settings, passwords, presets or customer configuration without recording the change and creating a backup where data could be affected.

SSH should be treated as a support/admin path. Disable it after handover when it is not needed, or restrict it to approved technician/support access where practical. For the full SSH policy decisions, see [RPI_SECURITY_BASELINE.md](RPI_SECURITY_BASELINE.md).

Secrets must not appear in logs, reports or support bundles:

- Do not log SSH credentials, admin passwords or private keys at any log level.
- Incident snapshots and support bundles are sanitized by `redact_event_dict()` before export.
- Before sharing any log file or support bundle externally, manually review it for secrets, private IPs and personal data.

## Simulation and Demo Mode

Simulation or demo mode must be disabled before validating production behaviour.

Before handover, confirm:

- runtime mode is production;
- camera IPs and VISCA IDs are real customer values;
- fake camera or fake ATEM status is not being used for production acceptance;
- `sim_ip_backup.json` is not masking the current configuration.

## Logs

Logs should help support without exposing secrets. Do not log:

- passwords or attempted passwords;
- private keys or licence secrets;
- raw customer backups;
- unnecessary personal data.

When sharing logs, include version, profile, time window and symptoms. Remove unrelated or sensitive lines.

## Legal and Compliance

This document is operational guidance. It does not make legal, regulatory, cybersecurity certification or compliance claims.
