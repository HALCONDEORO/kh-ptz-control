# Incident Classification

This document defines the first Hall PTZ Control incident taxonomy for support and product feedback.

Issue: #547.

The taxonomy starts as support/process documentation and can later be connected to support bundles, known-good comparisons, reports and maintenance workflows.

---

## Categories

Use a small taxonomy first:

| Category | Use when evidence suggests |
|---|---|
| `software_bug` | HALLPTZ code or packaged behaviour is defective. |
| `hardware_failure` | Camera, Raspberry Pi, ATEM, switch, touchscreen or other hardware failed. |
| `network_change` | IP, VLAN, DHCP, routing, cabling or network policy changed. |
| `customer_change` | Customer changed layout, preset, config, hardware placement or operation outside handover guidance. |
| `installer_error` | Setup, validation or handover was incomplete or wrong. |
| `configuration_error` | Config values are invalid, inconsistent or incomplete. |
| `unsupported_hardware` | Hardware is outside the approved or validated matrix. |
| `training_issue` | Operator action indicates missing or unclear training. |
| `documentation_gap` | Docs or handover did not explain the expected action or limitation. |
| `licence_or_support_issue` | Support entitlement, licence status or scope is unclear or invalid. |
| `third_party_av_change` | External AV provider changed ATEM, cabling, network or related environment. |
| `unknown` | Evidence is insufficient. |

Classification starts as suspected, not final blame. Support can override the final category after evidence review.

---

## Severity

| Severity | Meaning |
|---|---|
| `low` | Minor issue with no immediate customer risk. |
| `medium` | Usability or support issue that should be scheduled. |
| `high` | Significant customer impact or likely paid support impact. |
| `critical` | Live event risk, system unusable or customer-ready blocker. |

---

## Impact

| Impact | Meaning |
|---|---|
| `cosmetic` | Visible issue without operational impact. |
| `operator_inconvenience` | Slows or confuses the operator. |
| `reduced_functionality` | Some core workflow is degraded. |
| `live_event_risk` | Could disrupt a live service/event. |
| `system_unusable` | Operator cannot use the installation. |
| `customer_ready_blocked` | Blocks handover, pilot acceptance or customer-ready status. |

---

## Incident Record Fields

Suggested record shape:

```json
{
  "incident_id": "inc_2026_0001",
  "installation_id": "HALLPTZ-2026-0004",
  "reported_at": "2026-05-11T16:30:00Z",
  "category": "network_change",
  "severity": "high",
  "impact": "system_unusable",
  "source": "customer_call",
  "detected_by": "human",
  "summary": "Camera 2 unreachable after network change",
  "evidence": ["support_bundle", "hallptz_doctor", "handover_report"],
  "billable": true,
  "follow_up": "revalidation_required"
}
```

Required closeout fields:

- Final category.
- Severity.
- Impact.
- Customer-visible cause summary.
- Internal root cause notes.
- Billable yes/no/unknown.
- Follow-up issue needed yes/no.
- Product improvement needed yes/no.

---

## Billable Or Included Support

Classification should help decide:

- Included support.
- Billable revalidation.
- Onsite visit required.
- Customer training needed.
- Hardware replacement.
- Documentation improvement.
- Software bug fix priority.

Keep billing hints evidence-based. A suspected customer, network or third-party change is not proof by itself.

---

## Feedback Review

Review categories monthly or after every 10 incidents, whichever comes first.

Example monthly summary:

```text
40% network/customer changes -> improve known-good state and warranty wording
25% training issues -> improve operator handover/training mode
20% hardware failures -> tighten approved hardware matrix
10% software bugs -> prioritize fixes
5% unknown -> improve support bundle diagnostics
```

---

## Integration Points

Future integration points:

- Support bundle export.
- Support Bundle Reader.
- Known Good Room State.
- Warranty/support boundary.
- Maintenance plan.
- Installation report.
- Handover acceptance.
- `hallptz doctor`.
- Reseller/installer partner mode.

---

## Safety Rules

- Do not mark an incident as customer-caused without evidence.
- Do not use classification to hide real software defects.
- Keep customer-facing wording neutral.
- Do not include secrets or unnecessary personal data in incident records.
- Unknown is acceptable when evidence is insufficient.
