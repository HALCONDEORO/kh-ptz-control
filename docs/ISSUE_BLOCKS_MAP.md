# Issue dependency snapshot

This is a snapshot, not release approval or the source of truth.
GitHub owns current open issues and explicit dependency links.
Reads are not an atomic snapshot across API calls; changes during a check
can produce a mismatch or escape that particular observation.
Issue events do not cover every dependency edit: manual and release checks
catch changes at check time, not through an immediate dependency monitor.
Historical references in source/docs are not reconstructed as live issues.
Zero open issues does not imply no product gaps or hardware acceptance.

Refresh: `python3 scripts/check_issue_blocks_map.py --refresh`
Check: `python3 scripts/check_issue_blocks_map.py`
An API error or incomplete graph fails closed; it never becomes an empty map.
Freshness compares graph content, not elapsed time: unchanged old snapshots
remain valid; new/closed issues, title changes and dependency changes fail.

```json
{
  "schema_version": 1,
  "repository": "HALCONDEORO/kh-ptz-control",
  "recorded_at": "2026-11-15T22:06:59.160027+00:00",
  "issues": []
}
```
