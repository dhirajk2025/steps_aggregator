"""Plan subcommand: create Jira epic + tickets for each checklist step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import Config
from .exceptions import JiraNotFoundError
from .jira_client import JiraClient
from .models import ChecklistStep


def slugify(name: str) -> str:
    """Convert an API name to a label-safe slug."""
    return name.lower().replace(" ", "-").replace("/", "-").replace("_", "-")


def step_labels(step_id: str, api_slug: str, epic_key: str) -> list[str]:
    return ["api-checker", step_id, f"api-{api_slug}", f"epic-{epic_key.lower()}"]


def step_jql(project: str, step_id: str, api_slug: str) -> str:
    return (
        f'project = "{project}" AND labels = "api-checker" '
        f'AND labels = "{step_id}" AND labels = "api-{api_slug}"'
    )


def epic_jql(project: str, api_slug: str) -> str:
    return (
        f'project = "{project}" AND issuetype = Epic '
        f'AND labels = "api-checker" AND labels = "api-{api_slug}"'
    )


@dataclass
class PlanResult:
    epic_key: Optional[str]
    epic_created: bool
    steps: list[ChecklistStep]


def run(
    api_name: str,
    config: Config,
    client: JiraClient,
    pm_epic_key: Optional[str] = None,
    step_ids: Optional[list[str]] = None,
    dry_run: bool = False,
) -> PlanResult:
    """
    Create an IGAV epic for the API, then create checklist step tickets under it.

    If an epic for this API already exists (matched by label), it is reused.
    If pm_epic_key is provided, it is linked to the IGAV epic as a parent reference.
    """
    api_slug = slugify(api_name)

    # Validate PM epic if provided (skip in dry-run)
    if pm_epic_key and not dry_run:
        try:
            client.get_issue(pm_epic_key)
        except JiraNotFoundError:
            raise JiraNotFoundError(f"PM epic '{pm_epic_key}' not found in Jira.")

    # ── Step 1: Find or create the IGAV epic ─────────────────────────────────
    epic_key, epic_created = _find_or_create_epic(
        api_name=api_name,
        api_slug=api_slug,
        config=config,
        client=client,
        pm_epic_key=pm_epic_key,
        dry_run=dry_run,
    )

    # ── Step 2: Create checklist step tickets under the epic ──────────────────
    steps_to_create = config.steps
    if step_ids:
        steps_to_create = [s for s in config.steps if s.id in step_ids]

    created: dict[str, str] = {}  # step_id -> jira_key
    step_results: list[ChecklistStep] = []

    for step in steps_to_create:
        labels = step_labels(step.id, api_slug, epic_key or "pending")
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
            cs.evidence.append("Already exists — skipped creation")
            step_results.append(cs)
            continue

        summary = step.summary_template.format(api_name=api_name, epic_key=epic_key or pm_epic_key or "")
        description = step.description_template.format(
            api_name=api_name,
            epic_key=epic_key or pm_epic_key or "",
            step_name=step.name,
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
            cs.evidence.append(f"[dry-run] Would create under epic {epic_key or '(new epic)'}")
            step_results.append(cs)
        else:
            key = client.create_issue(payload)
            created[step.id] = key
            cs = ChecklistStep(definition=step, jira_key=key, status="created", summary=summary)
            cs.evidence.append("Created successfully")
            step_results.append(cs)

    # ── Step 3: Wire dependency links ─────────────────────────────────────────
    if not dry_run:
        for step in steps_to_create:
            if step.id not in created:
                continue
            inward_key = created[step.id]
            for blocked_id in step.blocks:
                if blocked_id in created:
                    try:
                        client.create_link(inward_key, created[blocked_id], link_type="Blocks")
                    except Exception:
                        pass  # Best-effort

    return PlanResult(epic_key=epic_key, epic_created=epic_created, steps=step_results)


def _find_or_create_epic(
    api_name: str,
    api_slug: str,
    config: Config,
    client: JiraClient,
    pm_epic_key: Optional[str],
    dry_run: bool,
) -> tuple[Optional[str], bool]:
    """Return (epic_key, was_created). Returns (None, False) in dry-run."""
    if dry_run:
        return None, False

    existing = client.search(
        epic_jql(config.jira.project, api_slug),
        fields=["summary"],
        max_results=1,
    )
    if existing:
        return existing[0]["key"], False

    epic_labels = ["api-checker", f"api-{api_slug}"]
    description = (
        f"API development epic for {api_name}.\n\n"
        f"Tracks all compliance checklist steps from due diligence through production deployment.\n"
        + (f"\nParent PM epic: {pm_epic_key}" if pm_epic_key else "")
    )
    epic_key = client.create_epic(
        project=config.jira.project,
        api_name=api_name,
        description=description,
        labels=epic_labels,
        pm_epic_key=pm_epic_key,
        epic_link_field=config.jira.epic_link_field,
    )
    return epic_key, True
