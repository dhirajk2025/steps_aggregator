"""Status subcommand: show live checklist progress for an API."""

from __future__ import annotations

from .config import Config
from .jira_client import JiraClient
from .models import ChecklistStep
from .plan import slugify, step_jql


def run(
    api_name: str,
    config: Config,
    client: JiraClient,
    epic_key: str | None = None,
    verbose: bool = False,
) -> list[ChecklistStep]:
    """Fetch current status of all checklist steps for an API."""
    api_slug = slugify(api_name)
    steps = config.steps
    status_map = config.jira_status_map
    results: list[ChecklistStep] = []

    for step in steps:
        jql = step_jql(config.jira.project, step.id, api_slug)
        if epic_key:
            epic_slug = epic_key.lower()
            jql += f' AND labels = "epic-{epic_slug}"'

        issues = client.search(jql, fields=["summary", "status", "resolution", "assignee", "updated"], max_results=1)

        if not issues:
            results.append(ChecklistStep(definition=step, status="missing"))
            continue

        issue = issues[0]
        fields = issue.get("fields", {})
        jira_status = fields.get("status", {}).get("name", "")
        resolution = fields.get("resolution", {})
        resolution_name = resolution.get("name") if isinstance(resolution, dict) else None
        assignee = fields.get("assignee") or {}
        assignee_name = assignee.get("displayName") if isinstance(assignee, dict) else None
        updated = fields.get("updated", "")

        mapped_status = status_map.get(jira_status, "in-progress")

        cs = ChecklistStep(
            definition=step,
            jira_key=issue["key"],
            status=mapped_status,
            assignee=assignee_name,
            resolution=resolution_name,
            summary=fields.get("summary", ""),
            updated=updated[:10] if updated else None,
        )
        results.append(cs)

    return results
