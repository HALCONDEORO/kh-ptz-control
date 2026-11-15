#!/usr/bin/env python3
# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
"""Compare a recorded issue graph with live GitHub issue dependencies.

Default mode checks only. --refresh writes a snapshot after all live reads
succeed. Neither mode changes issues, dependencies, labels or release state.
The map covers explicit GitHub dependencies, not prose or historical issue IDs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward an authenticated request to a redirected destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def get_pages(path: str) -> list[dict]:
    """Bounded pagination. Never send credentials to a server-provided URL."""
    result: list[dict] = []
    for page in range(1, 101):
        separator = "&" if "?" in path else "?"
        url = f"https://api.github.com{path}{separator}per_page=100&page={page}"
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(url, headers=headers)
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=30) as response:
            data = json.load(response)
            has_next = 'rel="next"' in response.headers.get("Link", "")
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise ValueError("GitHub list response has invalid structure")
        result.extend(data)
        if len(data) < 100 and not has_next:
            return result
        if not data:
            raise ValueError("GitHub advertised another page but returned no rows")
    raise ValueError("GitHub pagination limit exceeded; graph is incomplete")


def _identity(issue: dict) -> tuple[int, str, str]:
    number, title, url = issue.get("number"), issue.get("title"), issue.get("html_url")
    if type(number) is not int or number < 1 or not isinstance(title, str) or not title.strip():
        raise ValueError("GitHub issue number/title is malformed")
    if "pull_request" in issue:
        raise ValueError("dependency must be an issue, not a pull request")
    if not isinstance(url, str) or not re.fullmatch(rf"https://github\.com/[\w.-]+/[\w.-]+/issues/{number}", url):
        raise ValueError("GitHub issue URL is malformed")
    return number, title, url


def live_graph(repo: str) -> list[dict]:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("repository must be OWNER/REPO")
    records = []
    seen: set[int] = set()
    for issue in get_pages(f"/repos/{repo}/issues?state=open"):
        if "pull_request" in issue:
            continue
        number, title, url = _identity(issue)
        if issue.get("state") != "open" or number in seen:
            raise ValueError("GitHub open-issue response has closed/duplicate rows")
        if url.lower() != f"https://github.com/{repo}/issues/{number}".lower():
            raise ValueError("GitHub returned an issue from another repository")
        seen.add(number)
        blockers = []
        urls: set[str] = set()
        for blocker in get_pages(f"/repos/{repo}/issues/{number}/dependencies/blocked_by"):
            _, _, blocker_url = _identity(blocker)
            state = blocker.get("state")
            if state not in {"open", "closed"} or blocker_url in urls:
                raise ValueError("GitHub dependency state/identity is malformed")
            urls.add(blocker_url)
            blockers.append({"url": blocker_url, "state": state})
        records.append({"number": number, "title": title, "url": url,
                        "blocked_by": sorted(blockers, key=lambda row: row["url"])})
    return sorted(records, key=lambda row: row["number"])


def render(snapshot: dict) -> str:
    # Titles are JSON encoded in a fence, never interpreted as markup/code.
    return (
        "# Issue dependency snapshot\n\n"
        "This is a snapshot, not release approval or the source of truth.\n"
        "GitHub owns current open issues and explicit dependency links.\n"
        "Reads are not an atomic snapshot across API calls; changes during a check\n"
        "can produce a mismatch or escape that particular observation.\n"
        "Issue events do not cover every dependency edit: manual and release checks\n"
        "catch changes at check time, not through an immediate dependency monitor.\n"
        "Historical references in source/docs are not reconstructed as live issues.\n"
        "Zero open issues does not imply no product gaps or hardware acceptance.\n\n"
        "Refresh: `python3 scripts/check_issue_blocks_map.py --refresh`\n"
        "Check: `python3 scripts/check_issue_blocks_map.py`\n"
        "An API error or incomplete graph fails closed; it never becomes an empty map.\n"
        "Freshness compares graph content, not elapsed time: unchanged old snapshots\n"
        "remain valid; new/closed issues, title changes and dependency changes fail.\n\n"
        "```json\n" + json.dumps(snapshot, ensure_ascii=True, indent=2) + "\n```\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="HALCONDEORO/kh-ptz-control")
    parser.add_argument("--map", type=Path, default=ROOT / "docs/ISSUE_BLOCKS_MAP.md")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)
    try:
        graph = live_graph(args.repo)
        if args.refresh:
            snapshot = {"schema_version": 1, "repository": args.repo,
                        "recorded_at": datetime.now(timezone.utc).isoformat(), "issues": graph}
            content = render(snapshot)
            args.map.write_text(content, encoding="utf-8")
            print(f"Snapshot refreshed: {len(graph)} open issues (not release approval)")
            return 0
        text = args.map.read_text(encoding="utf-8")
        matches = re.findall(r"^```json\n(.*?)\n```$", text, re.M | re.S)
        if len(matches) != 1:
            raise ValueError("map must contain exactly one JSON snapshot")
        snapshot = json.loads(matches[0])
        if not isinstance(snapshot, dict) or set(snapshot) != {"schema_version", "repository", "recorded_at", "issues"}:
            raise ValueError("map snapshot schema is invalid")
        if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1 or snapshot["repository"] != args.repo:
            raise ValueError("map schema/repository mismatch")
        stamp = datetime.fromisoformat(snapshot["recorded_at"])
        if stamp.tzinfo is None or stamp > datetime.now(timezone.utc):
            raise ValueError("map timestamp must be timezone-aware and not in the future")
        if json.dumps(snapshot["issues"], sort_keys=True) != json.dumps(graph, sort_keys=True) or text != render(snapshot):
            print("ERROR: issue map is stale or its rendered content was changed; refresh after reviewing live changes")
            return 1
        print(f"Issue map matches live graph: {len(graph)} open issues (not release approval)")
        return 0
    except (OSError, ValueError, TypeError, urllib.error.URLError) as exc:
        # Never print response bodies, headers or environment values.
        print(f"ERROR: cannot verify complete issue graph ({type(exc).__name__}); fail closed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
