# AV Device Hardening Checklist

Use this checklist for cameras, ATEM devices, switches and routers used with KH PTZ Control installations.

This checklist is verification guidance. It does not automate vendor device configuration and does not require storing device passwords.

## Rules

```text
[ ] do not store device admin passwords in the repository
[ ] do not include device passwords in handover reports
[ ] do not include device passwords in support bundles
[ ] do not perform risky firmware updates during a live event setup
[ ] document unknown or not-applicable items instead of guessing
```

## Cameras

For each PTZ camera:

```text
[ ] model recorded
[ ] firmware version recorded
[ ] default admin password changed
[ ] static IP or DHCP reservation configured
[ ] camera role recorded
[ ] VISCA-over-IP control verified
[ ] camera is on the intended AV/control subnet
[ ] camera is not reachable from guest WiFi
[ ] cloud/P2P/vendor remote access disabled if not needed
[ ] UPnP disabled if present and not needed
[ ] RTSP/ONVIF/web access disabled if not required by the installation
[ ] firmware update considered and deferred if unsafe during setup
```

Record camera identity without secrets:

```text
Camera:
Role:
Model:
Firmware:
IP/subnet:
VISCA ID:
Notes:
```

## ATEM

For each ATEM device:

```text
[ ] model recorded
[ ] firmware/software version recorded
[ ] expected IP/subnet configured
[ ] required/optional state matches installation profile
[ ] reachable from Raspberry Pi when required
[ ] not exposed to guest/public networks
[ ] control path tested from the installed profile
[ ] absence handled correctly when ATEM is not part of the installation
```

Record ATEM identity without secrets:

```text
ATEM model:
Firmware/software:
IP/subnet:
Required: yes/no
Test result:
Notes:
```

## Switches And Routers

For the local AV/control network:

```text
[ ] admin password changed
[ ] default remote/WAN management disabled
[ ] management restricted to installer/admin network where practical
[ ] AV VLAN or isolated subnet configured where available
[ ] guest WiFi blocked from AV/control devices
[ ] used ports labelled where practical
[ ] model and firmware version recorded
[ ] configuration backup created where allowed
[ ] rollback/recovery access understood
```

Do not commit router or switch backup files unless they are sanitized examples.

## Network Exposure

Verify:

```text
[ ] Raspberry Pi is not directly exposed to public internet
[ ] cameras are not directly exposed to public internet
[ ] ATEM is not directly exposed to public internet
[ ] guest WiFi cannot control cameras or ATEM
[ ] support access is explicitly approved
```

If the site network cannot provide isolation, record it as a limitation before handover.

## Handover Status

Use this status for each item:

```text
verified
not applicable
warning
blocked
unknown
```

Do not mark an item verified unless the installer actually checked it.

## Follow-Up

Future reports may convert this checklist into structured installation evidence, but the first version is a human checklist for safe customer preparation.
