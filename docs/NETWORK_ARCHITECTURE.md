# KHPTZ AV VLAN — Reference Network Architecture

**Document scope:** recommended network architecture for KH PTZ Control
customer installations. This document is referenced by network diagnostics,
installer checklists, and support handover.

---

## Summary

KH PTZ Control must reliably reach three device classes over IP:

| Device class         | Typical address range  | Protocol       |
|----------------------|------------------------|----------------|
| PTZ cameras (VISCA)  | 192.168.30.x–40.x      | TCP/IP, VISCA  |
| ATEM switcher        | 192.168.30.x–40.x      | TCP/IP         |
| Raspberry Pi (KHPTZ)  | 192.168.30.x–40.x      | Operator UI    |

All three must be on the same subnet and must not be reachable by guest or
client devices.

---

## Recommended model: isolated AV VLAN

```
  Internet
     |
  WAN router / firewall
     |
  VLAN 30 — AV Control (192.168.30.0/24) ← KHPTZ subnet
     |                               |
  Raspberry Pi            PTZ cameras / ATEM
  192.168.30.10           192.168.30.20–30

  VLAN 1  — Guest WiFi / Client LAN  ← NO access to VLAN 30
```

### IP plan

| Device                | Recommended IP       |
|-----------------------|----------------------|
| Raspberry Pi (KHPTZ)   | 192.168.30.10        |
| PTZ Camera 1          | 192.168.30.20        |
| PTZ Camera 2          | 192.168.30.21        |
| ATEM switcher         | 192.168.30.30        |
| Gateway (if needed)   | 192.168.30.1         |

- Subnet mask: 255.255.255.0 (/24)
- DHCP: off on AV VLAN (static only) — see below
- DNS: not required (all communication is by IP)
- Internet: not required (KHPTZ is offline-first)

### Why static IPs

VISCA-over-IP and the ATEM SDK require stable IP addresses. DHCP lease
changes will break camera control mid-event. Use static assignment or
DHCP reservations by MAC address.

---

## Flat-network risk

Running KHPTZ on a flat or shared customer LAN increases risk:

- Guest or client devices may reach the Raspberry Pi.
- Users may access cameras directly over the LAN.
- Network faults on the shared LAN affect AV control.
- Support troubleshooting becomes harder (more traffic, more devices).

**If flat LAN cannot be avoided:** document this during installation handover.
The diagnostics system will warn the operator (WARNING, not FAIL by default).

---

## Required allow/deny flows

| Source           | Destination        | Ports          | Action |
|------------------|--------------------|----------------|--------|
| Raspberry Pi     | PTZ cameras        | TCP 5678 (default VISCA) | ALLOW  |
| Raspberry Pi     | ATEM switcher      | TCP/UDP (ATEM SDK)       | ALLOW  |
| Operator device  | Raspberry Pi UI    | TCP (touchscreen local)  | ALLOW  |
| Guest WiFi       | AV VLAN            | any            | DENY   |
| AV VLAN          | Internet           | any            | DENY (recommended) |

---

## Offline-first assumption

KH PTZ Control is designed for offline-first customer sites. The
application does not require internet access during normal operation. Cloud
connectivity (if ever added) will be opt-in and gated by
`runtime.connectivity_mode: online`.

Default: `runtime.connectivity_mode: offline`.

---

## VLAN configuration (IT reference)

- Create a dedicated VLAN for AV control (e.g. VLAN 30).
- Assign a /24 subnet (e.g. 192.168.30.0/24).
- Block inter-VLAN routing between AV VLAN and guest/client VLANs.
- Connect Raspberry Pi, cameras, and ATEM to the AV VLAN switch port/SSID.
- Assign static IPs to all AV devices.

If the site cannot support a dedicated VLAN, document this and ensure the
diagnostics flat-network warning is accepted and recorded during handover.

---

## Customer/installer checklist

Before sign-off:

- [ ] AV VLAN created and isolated from guest/client LAN
- [ ] Static IPs assigned to all AV devices
- [ ] Raspberry Pi can ping all cameras and ATEM switcher
- [ ] Guest WiFi cannot reach 192.168.30.x devices
- [ ] config.yaml has correct camera and ATEM IPs
- [ ] `khptz doctor` passes with no FAIL checks
- [ ] `khptz known-good mark` recorded after successful test
- [ ] Network profile recorded in config.yaml as `isolated_av_vlan`

---

*See also: docs/RUNTIME_PATH_CONTRACT.md, docs/SUPPORT_BUNDLE_CONTRACT.md*
