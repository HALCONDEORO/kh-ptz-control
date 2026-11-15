# Copyright (c) 2026 MACD Adaptive Limited.
# Licensed under the MIT License. See LICENSE in the repository root.
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import urllib.error

import pytest

SPEC = importlib.util.spec_from_file_location(
    "issue_map", Path(__file__).parents[1] / "scripts/check_issue_blocks_map.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def issue(n=1, **over):
    result = {"number": n, "title": f"Issue {n}", "state": "open",
              "html_url": f"https://github.com/HALCONDEORO/kh-ptz-control/issues/{n}"}
    result.update(over)
    return result


def snapshot(path, graph):
    data = {"schema_version": 1, "repository": "HALCONDEORO/kh-ptz-control",
            "recorded_at": datetime.now(timezone.utc).isoformat(), "issues": graph}
    path.write_text(m.render(data))
    return data


def test_empty_is_valid_only_when_live_source_confirms(tmp_path, monkeypatch):
    p = tmp_path / "map.md"
    snapshot(p, [])
    monkeypatch.setattr(m, "get_pages", lambda path: [])
    assert m.main(["--map", str(p)]) == 0


def test_pull_requests_are_excluded(monkeypatch):
    monkeypatch.setattr(m, "get_pages", lambda path: [issue(pull_request={})])
    assert m.live_graph("HALCONDEORO/kh-ptz-control") == []


def test_dependencies_are_read_and_sorted(monkeypatch):
    monkeypatch.setattr(m, "get_pages", lambda path: [issue(4), issue(2)] if "state=open" in path else [issue(3, state="closed")])
    graph = m.live_graph("HALCONDEORO/kh-ptz-control")
    assert [r["number"] for r in graph] == [2, 4]
    assert graph[0]["blocked_by"] == [{"url": issue(3)["html_url"], "state": "closed"}]


def test_added_issue_makes_empty_snapshot_stale(tmp_path, monkeypatch):
    p = tmp_path / "map.md"
    snapshot(p, [])
    monkeypatch.setattr(m, "get_pages", lambda path: [issue()] if "state=open" in path else [])
    assert m.main(["--map", str(p)]) == 1


@pytest.mark.parametrize("change", ["title", "blocked_by", "removed"])
def test_semantic_changes_are_stale(tmp_path, monkeypatch, change):
    p = tmp_path / "map.md"
    graph = [{"number": 1, "title": "Issue 1", "url": issue()["html_url"], "blocked_by": []}]
    snapshot(p, graph)
    changed = json.loads(json.dumps(graph))
    if change == "title":
        changed[0]["title"] = "New title"
    elif change == "blocked_by":
        changed[0]["blocked_by"] = [{"url": issue(2)["html_url"], "state": "open"}]
    else:
        changed = []
    monkeypatch.setattr(m, "live_graph", lambda repo: changed)
    assert m.main(["--map", str(p)]) == 1


def test_api_error_never_counts_as_empty_or_overwrites_snapshot(tmp_path, monkeypatch):
    p = tmp_path / "map.md"
    snapshot(p, [])
    before = p.read_bytes()

    def fail(path):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(m, "get_pages", fail)
    assert m.main(["--map", str(p)]) == 2
    assert m.main(["--map", str(p), "--refresh"]) == 2
    assert p.read_bytes() == before


def test_missing_map_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "get_pages", lambda path: [])
    assert m.main(["--map", str(tmp_path / "missing")]) == 2


@pytest.mark.parametrize("rows", [[issue(state="closed")], [issue(), issue()], [issue(number=True)], [issue(html_url="https://evil.example/issues/1")]])
def test_bad_issue_payload_fails_closed(monkeypatch, rows):
    monkeypatch.setattr(m, "get_pages", lambda path: rows)
    with pytest.raises(ValueError):
        m.live_graph("HALCONDEORO/kh-ptz-control")


def test_refresh_and_check_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "get_pages", lambda path: [])
    p = tmp_path / "map.md"
    assert m.main(["--map", str(p), "--refresh"]) == 0
    assert m.main(["--map", str(p)]) == 0
    p.write_text(p.read_text().replace("not release approval", "approved"))
    assert m.main(["--map", str(p)]) == 1


@pytest.mark.parametrize("text", ["no snapshot", "```json\n{}\n```\n", "```json\n{broken\n```\n"])
def test_malformed_snapshot_fails_closed(tmp_path, monkeypatch, text):
    monkeypatch.setattr(m, "get_pages", lambda path: [])
    p = tmp_path / "map.md"
    p.write_text(text)
    assert m.main(["--map", str(p)]) == 2


class Response:
    def __init__(self, data, link=""):
        self.data = json.dumps(data).encode()
        self.headers = {"Link": link}

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_pagination_does_not_follow_untrusted_urls(monkeypatch):
    calls = []

    def request(req, **kw):
        calls.append(req.full_url)
        if len(calls) == 1:
            return Response([issue()], '<https://evil.example/leak>; rel="next"')
        return Response([])

    monkeypatch.setattr(m.urllib.request, "urlopen", request)
    assert len(m.get_pages("/repos/HALCONDEORO/kh-ptz-control/issues?state=open")) == 1
    assert len(calls) == 2
    assert all(url.startswith("https://api.github.com/") for url in calls)
    assert calls[1].endswith("page=2")


def test_second_page_failure_is_not_partial_success(monkeypatch):
    calls = []

    def request(req, **kw):
        calls.append(req.full_url)
        if len(calls) == 1:
            return Response([issue()], '<https://api.github.com/next>; rel="next"')
        raise urllib.error.URLError("page 2 failed")

    monkeypatch.setattr(m.urllib.request, "urlopen", request)
    with pytest.raises(urllib.error.URLError):
        m.get_pages("/repos/HALCONDEORO/kh-ptz-control/issues?state=open")


def test_release_workflow_keeps_failure_and_checks_live_map():
    workflow = (Path(__file__).parents[1] / ".github/workflows/release-check.yml").read_text()
    assert "issues: read" in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert "run: python3 scripts/check_issue_blocks_map.py" in workflow
    assert "continue-on-error" not in workflow
    assert "--refresh" not in workflow


def test_snapshot_boolean_number_cannot_equal_integer(tmp_path, monkeypatch):
    p = tmp_path / "map.md"
    data = snapshot(p, [{"number": True}])
    monkeypatch.setattr(m, "live_graph", lambda repo: [{"number": 1}])
    p.write_text(m.render(data))
    assert m.main(["--map", str(p)]) == 1


def test_dependency_error_blocks_whole_graph(monkeypatch):
    def request(path):
        if "state=open" in path:
            return [issue()]
        raise urllib.error.HTTPError("https://api.github.com/", 403, "forbidden", {}, None)

    monkeypatch.setattr(m, "get_pages", request)
    with pytest.raises(urllib.error.HTTPError):
        m.live_graph("HALCONDEORO/kh-ptz-control")
