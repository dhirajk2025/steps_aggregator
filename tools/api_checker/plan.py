"""Plan subcommand: create Jira tickets for each checklist step."""

from __future__ import annotations

from typing import Optional

from .config import Config
from .exceptions import JiraNotFoundError
from .jira_client import JiraClient
from .models import ChecklistStep


def slugify(name: str) -> str:
    """Convert an API name to a label-safe slug."""
    return name.lower().replace(" ", "-").replace("/", "-").replace("_", "-")


def step_labels(step_id: str, api_slug: str, epic_slug: str) -> list[str]:
    return ["api-checker", step_id, f"api-{api_slug}", f"epic-{epic_slug}"]


def step_jql(project: str, step_id: str, api_slug: str) -> str:
    return (
        f'project = "{project}" AND labels = "api-checker" '
        f'AND labels = "{step_id}" AND labels = "api-{api_slug}"'
    )


def run(
    api_name: str,
    epic_key: str,
    config: Config,
    client: JiraClient,
    step_ids: Optional[list[str]] = None,
    dry_run: bool = False,
) -> list[ChecklistStep]:
    """Create Jira tickets for the checklist steps. Returns created/skipped steps."""
    # Validate epic exists (skip in dry-run)
    if not dry_run:
        try:
            client.get_issue(epic_key)
        except JiraNotFoundError:
            raise JiraNotFoundError(f"Epic '{epic_key}' not found in Jira.")

    api_slug = slugify(api_name)
    epic_slug = epic_key.lower().replace("-", "").replace("_", "")
    # Keep epic slug readable: pm-1313 → pm-1313
    epic_slug = epic_key.lower()

    steps_to_create = config.steps
    if step_ids:
        steps_to_create = [s for s in config.steps if s.id in step_ids]

    created: dict[str, str] = {}  # step_id -> jira_key
    results: list[ChecklistStep] = []

    for step in steps_to_create:
        labels = step_labels(step.id, api_slug, epic_slug)
        jql = step_jql(config.jira.project, step.id, api_slug)
        existing = client.search(jql, fields=["summary", "status", "assignee"], max_results=1)

        if existing:
            existing_key = existing[0]["key"]
            created[step.id] = existing_key
            cs = ChecklistStep(
                definition=step,
                jira_key=existing_key,
                status="skipped",
                summary=existing[0]["fields"].get("summary", ""),
            )
            cs.evidence.append(f"Already exists — skipped creation")
            results.append(cs)
            continue

        summary = step.summary_template.format(api_name=api_name, epic_key=epic_key)
        description = step.description_template.format(
            api_name=api_name, epic_key=epic_key, step_name=step.name
        )

        payload = client.build_issue_payload(
            project=config.jira.project,
            summary=summary,
            description=description,
            issue_type=step.issue_type,
            labels=labels,
            epic_key=epic_key,
            epic_link_field=config.jira.epic_link_field,
        )

        if dry_run:
            created[step.id] = f"DRY-{step.order}"
            cs = ChecklistStep(definition=step, jira_key=None, status="dry-run", summary=summary)
            cs.evidence.append(f"[dry-run] Would create: {summary}")
            results.append(cs)
        else:
            key = client.create_issue(payload)
            created[step.id] = key
            cs = ChecklistStep(definition=step, jira_key=key, status="created", summary=summary)
            cs.evidence.append(f"Created successfully")
            results.append(cs)

    # Wire dependency links
    if not dry_run:
        for step in steps_to_create:
            if step.id not in created:
                continue
            inward_key = created[step.id]
            for blocked_id in step.blocks:
                if blocked_id in created:
                    outward_key = created[blocked_id]
                    try:
                        client.create_link(inward_key, outward_key, link_type="Blocks")
                    except Exception:
                        pass  # Link creation is best-effort

    return results
