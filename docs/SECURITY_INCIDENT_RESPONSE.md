# Security Incident Response Checklist

Use this checklist when a security issue is suspected during development, deployment or support.

This is practical operational guidance. It is not a legal, compliance or breach-notification policy.

## First Actions

```text
[ ] stop sharing affected files or logs
[ ] preserve evidence without changing the affected system more than necessary
[ ] notify the maintainer or authorized support contact
[ ] create a private internal record
[ ] do not paste secrets, raw customer data or exploit details into public issues
[ ] decide whether customer access, SSH access or support access must be paused
```

## Evidence To Preserve

Preserve:

```text
installed version/tag/commit
time and timezone
customer/site identifier in sanitized form
hallptz version output
hallptz doctor summary with secrets removed
relevant log time window with secrets removed
actions taken before and after discovery
affected files by path, not by secret contents
```

Do not preserve by copying secrets into GitHub, chat or email.

## What Not To Do

```text
[ ] do not delete evidence before recording what happened
[ ] do not rotate credentials before confirming which systems depend on them
[ ] do not post support bundles without checking them
[ ] do not continue remote access if compromise is suspected
[ ] do not promise legal or compliance outcomes from this checklist
```

## Secret Committed To GitHub

```text
[ ] stop using the exposed secret
[ ] rotate or revoke it in the system that trusts it
[ ] remove the secret from the working tree
[ ] open a private/sanitized follow-up issue
[ ] decide whether Git history cleanup is practical and necessary
[ ] audit logs for use of the exposed secret
[ ] add a repo hygiene or secret-scan rule if missing
```

Never rely on deleting a file from the latest commit as the only remediation. Assume anyone with repository access during exposure could have copied it.

## Customer Support Bundle Contains Sensitive Data

```text
[ ] stop distributing the bundle
[ ] identify who received it
[ ] create a sanitized replacement if support still needs data
[ ] remove passwords, private keys, tokens, raw backups and unnecessary personal data
[ ] review the bundle generation process before using it again
[ ] create a follow-up issue with paths and categories only
```

Use `docs/SUPPORT_RUNBOOK.md` for support handling and backup safety.

## Raspberry Pi Stolen Or Lost

```text
[ ] record installed version and customer site
[ ] assume local customer config and logs may be exposed
[ ] revoke or rotate credentials used by the device
[ ] disable or rotate SSH/support access
[ ] prepare replacement install from an approved release candidate or tag
[ ] restore only from a trusted backup
[ ] record whether any licence material was on the device
```

Do not reuse a recovered device for customer operation until it has been rebuilt or validated.

## SSH Access Suspected Compromised

```text
[ ] disable or restrict SSH if operationally safe
[ ] rotate affected SSH keys and passwords
[ ] inspect authorized_keys and user accounts
[ ] check recent login history
[ ] run hallptz doctor when the system is stable
[ ] create a backup before corrective changes that affect customer data
[ ] review firewall and support access policy
```

If customer operation would be interrupted, coordinate the change window before locking down access.

## Licence Private Key Leaked

```text
[ ] stop using the exposed signing key
[ ] generate a replacement key pair in a secure location
[ ] mark releases/licences signed by the old key as needing review
[ ] plan migration for installed systems
[ ] do not publish the private key or sample tokens in the issue
[ ] document the impact and replacement process privately
```

Public issues may reference that a key rotation is needed, but must not include key material.

## Customer Config Exposed

```text
[ ] remove the exposed file from distribution
[ ] identify exposed data categories
[ ] sanitize any follow-up issue
[ ] rotate passwords or tokens if included
[ ] consider IP plans, room names and support details sensitive
[ ] replace examples with fake sample configs
```

Real customer configs belong in runtime/customer storage, not in the repository.

## Malicious Or Failed Update Suspected

```text
[ ] record current version/tag/commit
[ ] disconnect remote access if compromise is suspected
[ ] create a backup if safe
[ ] preserve update logs
[ ] rollback to a known-good tag if needed
[ ] run hallptz doctor after rollback
[ ] compare deployed commit with the approved release source
```

Use `docs/RELEASE_PROCESS.md` and `docs/UPDATE_ROLLBACK.md` for release and rollback handling.

## Sanitized Follow-Up Issue Template

Use a private issue when possible. Keep it sanitized:

```text
Incident type:
Discovery date/time/timezone:
Affected version/tag/commit:
Affected area:
Customer data involved: none / sanitized category only
Secrets involved: none / rotated / pending rotation
Immediate action taken:
Evidence preserved:
Rollback/restore needed:
Follow-up fix:
What must not be posted publicly:
```

## Closeout

Before closing the incident:

```text
[ ] exposed credentials rotated or explicitly confirmed not exposed
[ ] customer/support access reviewed
[ ] affected release or installation recorded
[ ] backup/restore impact reviewed
[ ] follow-up issues created without secrets
[ ] documentation or tooling updated if prevention was missing
```
