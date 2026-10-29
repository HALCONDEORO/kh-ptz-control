# ATEM Manual Integration Plan

This document is the planning source of truth for the first Blackmagic ATEM integration phase.

Issue: #545.

Phase 1 customer-facing wording:

```text
Manual ATEM control integration
```

Do not market Phase 1 as automatic ATEM camera switching. Automatic preview or cut workflows remain future work and must not be enabled until manual ATEM control is stable, tested and validated on real hardware.

---

## Current Decision

ATEM support is optional and commercially safe only when treated as a manual control module.

Minimum viable ATEM support includes:

- ATEM can be absent without breaking PTZ camera control.
- ATEM configuration is centralised and validated.
- Status, Program and Preview can be read.
- Manual Preview commands are available for configured camera roles.
- CUT and AUTO are hidden or disabled by default for normal operator mode.
- CUT and AUTO are available only in admin, installer or support contexts where policy allows them.
- No seat/preset action automatically switches Program or Preview in Phase 1.
- Fake ATEM tests exist for hardware-free validation.
- Real hardware validation is recorded before any customer-ready ATEM claim.
- Handover records ATEM model, firmware/software, IP, mapping, test results and limitations.
- A rollback or kill switch can disable ATEM without deleting mapping.

---

## Commercial Dependency Policy

The initial implementation must choose one dependency path before production code is added.

Allowed candidates to evaluate:

- Python/OpenSwitcher-style integration such as `pyatem`, if licence and maintenance risk are acceptable.
- Node sidecar using `atem-connection`, if operational complexity is justified.
- Blackmagic official SDK where practical for the target Raspberry Pi deployment.

Rules:

- Do not use an unpinned latest dependency for customer installs.
- Do not make the app crash when the ATEM dependency is missing.
- `hallptz doctor` must report missing or incompatible ATEM dependency state.
- Runtime must stay LAN-local and offline-first.
- App, dependency or ATEM firmware/software updates require revalidation before customer-ready ATEM support resumes.
- Avoid PyATEMMax as the default commercial dependency unless licence review approves it.

The selected dependency, version range, licence notice location, fallback path and rollback policy must be recorded before implementation issues are opened.

---

## Architecture Boundary

Target boundary:

```text
UI
-> ApplicationController / service boundary
-> AtemService
-> AtemCommandContract
-> AtemPort
-> concrete ATEM adapter/library/SDK
-> Blackmagic ATEM
```

Rules:

- UI must not import the concrete ATEM library.
- ATEM failure must not break PTZ camera control.
- Read and write capabilities must be separate.
- Read-only diagnostics must not send live switching commands.
- External ATEM changes update ATEM state only; they must not move cameras.
- `FakeAtemPort` must support tests without hardware.

---

## Command Contract

Phase 1 allowed commands:

```text
read_status
read_program
read_preview
set_preview
cut
auto
test_connection
disconnect
```

Command results should use a standard shape:

```text
ok
command
target/input
atem_state
duration_ms
correlation_id
error_code
message
who/role for admin or support live actions
```

Safety rules:

- Read commands may retry with bounded timeout.
- `set_preview` may verify Preview after send.
- CUT must never retry automatically.
- AUTO must never retry automatically.
- No exception does not equal verified success.
- Admin/support live actions should be auditable.

Verification rules:

- `set_preview` verifies Preview equals requested input where possible.
- CUT verifies Program equals previous Preview where possible.
- AUTO verifies final Program after a bounded transition window where possible.

Events should distinguish HALLPTZ commands from external ATEM changes:

```text
HALLPTZ_ATEM_COMMAND_REQUESTED
HALLPTZ_ATEM_COMMAND_RESULT
EXTERNAL_ATEM_PROGRAM_CHANGED
EXTERNAL_ATEM_PREVIEW_CHANGED
```

---

## Configuration Model

ATEM configuration should live in canonical config, not scattered legacy files such as `ATEMIP.txt`.

Candidate shape:

```yaml
atem:
  installed: false
  enabled: false
  disabled_reason: null
  ip: 192.168.30.30
  me: 0
  inputs:
    cam1:
      input_id: 1
      label: Platform
    cam2:
      input_id: 2
      label: Comments
  startup_connect: true
  connect_timeout_seconds: 5
  command_timeout_seconds: 2
  reconnect_interval_seconds: 5
  reconnect_backoff_max_seconds: 30
  require_confirm_for_live_actions: false
  protocol:
    schema_version: 1
    command_contract_version: 1
  automation:
    enabled: false
    auto_switch_presets: false
```

Meaning:

- `installed`: the site physically has ATEM hardware or ATEM is part of the package.
- `enabled`: HALLPTZ actively connects to or controls the ATEM.
- `disabled_reason`: maintenance, customer disabled, support disabled, not in package or other.

Rules:

- `installed=true` does not cause connection attempts by itself.
- `enabled=true` is required before active control.
- `installed=false` plus `enabled=true` is invalid unless a future policy explicitly allows it.
- Phase 1 supports one configured M/E, default `0`.
- Multi-M/E support is future and unsupported unless validated.
- Config changes should use draft, validate and commit flow.
- Previous ATEM config snapshots should be kept before risky changes.

---

## State Model

Use explicit states instead of booleans:

```text
NOT_INSTALLED
DISABLED
MAINTENANCE
CONFIG_MISSING
CONFIG_INVALID
DEPENDENCY_MISSING
DEPENDENCY_INCOMPATIBLE
CONNECTING
ONLINE
OFFLINE
ERROR
RECONNECTING
ERROR_COOLDOWN
UNSUPPORTED
UNVERIFIED
UNKNOWN
```

Rules:

- Last known Program/Preview may be shown but must be marked stale.
- Stale state must never enable CUT or AUTO.
- Unsupported or unverified ATEM must not be marked customer-ready.
- External Program/Preview changes are normal state updates, not errors.
- Maintenance mode is not an error but requires revalidation before returning to ready.

---

## UI Behaviour

Normal operator mode:

- May show compact ATEM status if useful.
- Hides or disables CUT/AUTO by default.
- Avoids IP, library and diagnostic detail.

Admin, installer and support mode may show:

- ATEM status.
- Program and Preview.
- Preview Platform / Preview Comments or configured role names.
- CUT / AUTO only when ONLINE and safety checks pass.
- Input mapping and labels.
- IP/subnet.
- Library/dependency version.
- Last error.
- Copyable ATEM status.
- Kill switch / disable ATEM integration.
- Maintenance mode reason.

UI rules:

- Statuses must be text-first, not colour-only.
- Use role labels instead of raw camera numbers where possible.
- Disabled buttons must expose the reason.
- CUT/AUTO must be separated from high-frequency seat buttons.
- AUTO text must say it uses the ATEM current transition settings.
- Operator-facing UI and customer handover should be English by default for Ireland installs.

---

## Safety And Support Policy

Required safeguards:

- Background connect/reconnect.
- Bounded timeouts.
- Safe startup gate.
- Watchdog.
- Rate limit manual commands.
- Circuit breaker after repeated failures.
- Explicit degraded mode.
- No ATEM dependency for Emergency, Home or Stop.
- Disable live commands while editing ATEM config.
- No CUT/AUTO on startup or reconnect.
- Remote support is read-only by default.
- Explicit authorisation is required for remote CUT/AUTO.

Degraded wording:

```text
ATEM unavailable - camera controls still available
```

Event-in-progress restrictions:

- No ATEM config editing.
- No dependency update.
- No firmware/software update.
- No ATEM enable/disable change.
- No input remapping.
- No M/E changes.
- Read-only diagnostics only unless a permitted live control is deliberately used.

Admin/support live action audit fields:

```text
who
role/mode
when
action
result
correlation_id
ATEM state before/after where available
customer/admin authorisation where relevant
```

---

## Network And Environment Policy

Validate ATEM as part of the unified AV environment:

- Raspberry Pi.
- PTZ cameras.
- ATEM.
- AV switch/router/VLAN.
- Ethernet cabling.
- Operator touchscreen.
- Support/admin access path.

Network rules:

- Prefer dedicated AV network/VLAN.
- Prefer wired Ethernet.
- Raspberry Pi, cameras and ATEM should use static IPs or DHCP reservations.
- Warn if Wi-Fi, guest, office, printer or general LAN is part of the control path.
- Diagnostics/preflight should check reachability and likely subnet mismatch where practical.

Environment and handover must record:

- Connection path.
- AV switch/router model.
- Expected and actual IP range/subnet.
- UPS/SAI versus mains power.
- Rack/cabling photo attached or declined.
- Critical cable labels confirmed.
- Third-party ATEM Software Control allowed yes/no/unknown.
- Ownership for ATEM, network/VLAN and cabling.
- Warning acknowledged that changing IPs, cables, firmware or mapping may break integration.
- Last successful validation date, technician, app version and hardware/software versions.

---

## Customer-Ready Gate

ATEM support cannot be marked customer-ready until the unified PTZ + ATEM environment passes validation or limitations are explicitly accepted.

Validation checklist:

- Raspberry Pi network identity.
- PTZ camera reachability.
- ATEM reachability.
- Camera role mapping.
- ATEM input mapping.
- Preview Platform/Cam1.
- Preview Comments/Cam2.
- Wrong-mapping visual confirmation.
- CUT/AUTO by admin/installer if allowed.
- ATEM disconnect/reconnect test.
- Camera control still works while ATEM is offline.
- Startup with ATEM disconnected.
- Startup with wrong ATEM IP.
- Full AV reboot/power-cycle where practical.
- ATEM Software Control coexistence where practical.
- Simulated live event before selling ATEM support.
- Warnings and limitations recorded.

Blocking examples:

- ATEM unreachable while enabled.
- Input mapping not validated.
- Unsupported or unvalidated model when ATEM support is sold.
- Wrong subnet or unreachable network path.
- Program/Preview read failed.
- Required CUT/AUTO test skipped.
- Physical disconnect/reconnect recovery failed.
- PTZ control fails when ATEM is offline.

Warning examples:

- No UPS/SAI.
- Shared office switch.
- Third-party ATEM Software Control allowed.
- Rack/cabling photo declined.
- Firmware newer than tested but basic validation passed.
- Full AV reboot skipped with reason.
- Wi-Fi detected but accepted as custom risk.
- Customer-provided ATEM accepted with limitations.

---

## Handover Fields

Minimum ATEM handover/report fields:

- ATEM installed yes/no.
- ATEM enabled yes/no.
- ATEM disabled/maintenance reason if applicable.
- ATEM model.
- ATEM firmware/software version.
- Who may update ATEM firmware/software.
- Revalidation required after firmware/software update yes/no.
- Blackmagic SDK/software baseline where applicable.
- ATEM IP/subnet/VLAN.
- Configured M/E.
- ATEM input mapping and aliases.
- Program/Preview read test result.
- Preview Platform/Cam1 test result.
- Preview Comments/Cam2 test result.
- CUT/AUTO test result if performed.
- Disconnect/reconnect recovery test result.
- Full AV reboot/power-cycle result if performed.
- ATEM Software Control coexistence result if performed.
- Simulated live event result if performed.
- Latency readings/warnings where available.
- Known limitations.
- Unsupported/custom warnings accepted yes/no.
- Rack/cabling photo status.
- Cable labelling status.
- Ownership/responsibility notes.
- Last successful validation stamp.

---

## Rollback And Kill Switch

Expected behaviour:

```text
Disable ATEM integration
-> atem.enabled=false
-> no connection attempts
-> ATEM controls hidden/disabled
-> diagnostics reports ATEM disabled by config
-> PTZ controls continue working
```

Rules:

- The kill switch must not delete ATEM config or mapping.
- Re-enabling should require validation where appropriate.
- If an update breaks ATEM, disable the module, preserve PTZ, roll back app/dependency where possible and revalidate before enabling.

---

## Brand And Legal Wording

Candidate wording for legal/commercial review:

```text
Blackmagic Design and ATEM are third-party products. Hall PTZ Control integrates with supported/tested ATEM devices but is not an official Blackmagic product unless separately agreed.
```

---

## Future Issue Split

Recommended future slices:

1. Evaluate commercial ATEM dependency and record decision.
2. Move ATEM config into canonical config schema.
3. Create AtemPort, FakeAtemPort, dry-run and command contract.
4. Implement read-only ATEM connection and diagnostics service.
5. Implement manual ATEM write commands with safety guards.
6. Add manual ATEM UI panel.
7. Add ATEM no-automation regression tests.
8. Document ATEM installation, troubleshooting and handover wording.
9. Add real hardware ATEM validation report.
10. Prepare future auto-preview architecture without enabling it.

Dependency order:

```text
dependency decision
-> config schema
-> AtemPort/FakeAtemPort/command contract
-> read-only service
-> manual write service
-> manual UI
-> no-automation tests
-> handover/troubleshooting docs
-> real hardware validation
-> future automation safety
```

Duplicate issue rules:

- Do not create separate ATEM protocol/error/correlation issues outside the command contract.
- Do not create retry/verification work outside the manual command service.
- Do not rename legacy config files outside canonical config work.
- Do not duplicate ATEM handover status outside support/report docs.
- Do not pull auto-preview or auto-cut into manual ATEM integration.
