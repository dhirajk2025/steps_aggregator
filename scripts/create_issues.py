#!/usr/bin/env python3
"""
Creates GitHub issues for detected Confluence process changes.
Reads /tmp/monitor-report.json written by monitor.py.

Usage (called by GitHub Actions workflow):
    python3 scripts/create_issues.py

Environment variables required:
    GITHUB_TOKEN   - GitHub token (auto-set by Actions)
    GITHUB_REPO    - owner/repo (e.g. dhirajk2025/steps_aggregator)
"""

import json
import os
import sys
from pathlib import Path

import requests

REPORT_FILE = Path("/tmp/monitor-report.json")


def create_issue(token: str, repo: str, title: str, body: str) -> str:
    url = f"https://api.github.com/repos/{repo}/issues"
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        },
        json={"title": title, "body": body, "labels": ["process-update", "compliance"]},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["html_url"]



def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPO")
    if not token or not repo:
        print("ERROR: GITHUB_TOKEN and GITHUB_REPO must be set", file=sys.stderr)
        sys.exit(1)

    if not REPORT_FILE.exists():
        print(f"No report file found at {REPORT_FILE}")
        return

    with open(REPORT_FILE) as f:
        report = json.load(f)

    for change in report.get("changes", []):
        phases = "\n".join(f"- {p}" for p in change["affected_phases"]) or "- (unknown - review manually)"
        title = (
            f"Process Update: {change['title']} changed "
            f"(v{change['old_version']} to v{change['new_version']})"
        )
        body = f"""\
## Process Document Updated

**Page:** [{change['title']}]({change['page_url']})
**Version change:** v{change['old_version']} to v{change['new_version']}
**Detected:** {report['run_date']}

## What Changed

{change['summary']}

## Affected Checklist Phases

{phases}

## Action Required

Review the updated Confluence page and update Beads checklist tasks if the process changed.

- [ ] Review the Confluence page
- [ ] Update Beads checklist tasks if needed
- [ ] Close this issue when reviewed
"""
        url = create_issue(token, repo, title, body)
        print(f"Created issue: {url}")

    for j in report.get("jira_epic_changes", []):
        phase = f" [{j['phase']}]" if j.get("phase") else ""
        title = f"Jira Epic Status Change: {j['epic_key']} → {j['new_status']}{phase}"
        owner_line = f"\n**Owner:** {j['owner']}" if j.get("owner") else ""
        body = f"""\
## Jira Epic Status Changed

**Epic:** [{j['epic_key']} — {j['title']}]({j['url']})
**Status change:** {j['old_status']} → {j['new_status']}
**Phase:** {j.get('phase', 'unknown')}
**Detected:** {report['run_date']}{owner_line}

## Action Required

Review whether this epic's new status requires updating Beads checklist tasks or compliance artifacts.

- [ ] Review the Jira epic
- [ ] Update Beads checklist tasks if needed
- [ ] Close this issue when reviewed
"""
        url = create_issue(token, repo, title, body)
        print(f"Created issue: {url}")


if __name__ == "__main__":
    main()
