# Raspberry Pi Security Baseline

This baseline defines optional local security expectations for Raspberry Pi appliance/customer mode.

It is documentation first. Do not apply firewall rules automatically until the recovery path and Raspberry Pi validation are proven.

## Goals

```text
[ ] avoid exposing unnecessary services
[ ] keep camera and ATEM control working on the local AV network
[ ] support offline-capable installations
[ ] keep technician recovery possible
[ ] avoid locking out support during setup
```

## Network Assumptions

Preferred customer setup:

```text
Raspberry Pi, PTZ cameras and ATEM on a dedicated local AV/control network
static IPs or DHCP reservations for cameras and ATEM
no direct public internet exposure for the Raspberry Pi
guest WiFi cannot reach AV/control devices
internet not required for normal offline operation
```

## Firewall Baseline

Initial firewall policy:

```text
[ ] block unsolicited inbound traffic by default
[ ] allow SSH only when needed
[ ] restrict SSH to technician/support IPs where practical
[ ] do not expose app ports unless explicitly required
[ ] allow outbound LAN traffic needed for cameras and ATEM
[ ] allow DNS/NTP only when the installation profile requires them
[ ] document how to disable or revert firewall rules before enabling them
```

## SSH Policy

SSH is a support and administration path — not a normal operator feature.
Normal camera control operation does not require SSH.

### Default state

**SSH is disabled by default for customer/production installs.**

Enable SSH only when a technician needs remote access for setup or support.
Disable it again after the session ends when the installation is a fixed-site,
unattended appliance.

Technician/staging installs may leave SSH enabled if the site requires remote
administration, provided the rules below are applied.

### Authentication

- Password login over SSH is **not permitted** for customer installs.
  Enable key-based authentication only (`PasswordAuthentication no` in `sshd_config`).
- Root SSH login is **disabled** (`PermitRootLogin no`).
- The default Raspberry Pi OS `pi` user must be **disabled or removed** before handover.
  Create a named technician user instead.
- Temporary installer credentials must be removed before handover.

### Credential storage

- Do not store SSH private keys, passwords or passphrases in:
  - this repository or any git-tracked file
  - support bundles or support reports
  - handover documents sent to customers
  - logs (`journald`, application, or diagnostic output)
- Keep private keys on the technician's own secure device.
- Use SSH agent forwarding (`-A`) only on trusted networks.

### Support access workflow

When SSH access is needed for remote support:

1. Customer or site owner explicitly permits the session.
2. Technician enables SSH or opens firewall access.
3. Technician authenticates with their named key — no shared keys.
4. All actions during the session are recorded internally.
5. Technician closes SSH and removes temporary access when the session is complete.
6. Customer is informed the session has ended.

Never retain persistent remote access without the customer's explicit ongoing consent.

### Revocation

- When a technician's role ends, revoke their key from all customer devices.
- If a key is suspected compromised, rotate it across all installations immediately.
- Keep a list of which technician keys are authorised for which sites.

### Recovery fallback

Before disabling SSH:

- Confirm local touchscreen/console access works.
- Confirm the admin password for local GUI login is known.
- Record the current SSH state so it can be restored if remote access is needed.
- Test that disabling SSH does not break any monitoring or alerting.

If there is no local recovery path, do not disable SSH until one exists.

### Rate-limiting and logging

When SSH is enabled:

- Use `fail2ban` or equivalent to rate-limit failed login attempts (recommended,
  deferred to automation once Raspberry Pi validation is complete).
- SSH login attempts are logged by the OS (`/var/log/auth.log` or `journalctl`).
- Do not suppress SSH authentication logs.
- If the installation has centralised logging, forward auth events there.

## Ports

Known required inbound ports:

```text
none by default for normal local touchscreen operation
```

Known outbound/local network needs:

```text
VISCA-over-IP camera control
ATEM control when the installation profile uses ATEM
DNS/NTP only when configured and available
package downloads only during online setup/update
```

If a future feature exposes a local web API or remote support service, document the port, authentication and disable path before enabling it for customers.

## Offline Mode

Offline installations must continue to operate without internet access after setup.

Offline expectations:

```text
[ ] normal camera control works
[ ] local config is available
[ ] logs and backups stay local
[ ] diagnostics do not report missing internet as a failure
[ ] updates use approved offline media or a controlled technician process
```

## Recovery Before Restriction

Before applying restrictive firewall rules:

```text
[ ] confirm local console/touchscreen access works
[ ] confirm admin password or recovery access
[ ] record current network settings
[ ] create a backup
[ ] keep a tested disable command or rollback path
[ ] validate cameras and ATEM after applying rules
```

If there is no recovery path, do not apply restrictive rules on a customer system.

## Installer And Automation

Firewall automation is deferred until Raspberry Pi validation proves:

```text
[ ] rules do not break camera control
[ ] rules do not break ATEM control
[ ] rules do not break offline mode
[ ] rollback is tested
[ ] support can recover from a bad rule set
```

Future automation may live under:

```text
runtime/security/
```

Automation must be opt-in until it has passed release-candidate validation.

## Handover Checklist

Before handover:

```text
[ ] SSH state recorded
[ ] firewall state recorded
[ ] customer told not to expose the Raspberry Pi to public internet
[ ] camera/ATEM network reachability verified
[ ] guest WiFi isolation checked where applicable
[ ] recovery path documented internally
```
