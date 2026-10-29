# Definition of Ready

This document defines when an issue is ready to implement.

The goal is to avoid vague issues, hidden dependencies and work that starts before scope, risk and validation are clear.

---

## Global Definition of Ready

An issue is ready for implementation only when it has:

- Parent issue, epic or roadmap item.
- Dependencies listed in `Depends on`.
- Issues it blocks, or related issues, listed in `Blocks / Related`.
- Acceptance criteria written as a concrete checklist.
- Status, risk and type selected or stated.
- Tests expected, including automated, manual, hardware, simulation or `not applicable`.

---

## Required fields

Use these fields before assigning implementation work:

```text
Parent:
Depends on:
Blocks / Related:
Acceptance criteria:
Status:
Risk:
Type:
Tests expected:
```

`None` or `not applicable` is acceptable only when that is intentional and visible.

---

## Quality bar

A ready issue should answer:

- What problem is being solved?
- Why now?
- What is explicitly in scope?
- What is explicitly out of scope?
- What would make the issue accepted?
- What tests or checks should prove it?
- What risk remains if the work is wrong?

---

## Rule

If parent, dependencies, acceptance criteria, status, risk, type or expected tests are unclear, clarify the issue before implementation starts.
