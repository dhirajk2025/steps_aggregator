"""Audit subcommand: compliance report for an API (strict or fuzzy mode)."""

from __future__ import annotations

from datetime import datetime, timezone

from .config import Config
from .jira_client import JiraClient
from .models import AuditResult, ChecklistStep, RequiredArtifact
from .plan import slugify, step_jql


def run(
    api_name: str,
    config: Config,
    client: JiraClient,
    epic_key: str | None = None,
    fuzzy: bool = False,
) -> AuditResult:
    """
    Produce a compliance audit report.

    strict mode (default): queries by api-checker labels only.
    fuzzy mode: if no labeled tickets found, falls back to keyword search
                across all IGAV tickets under the epic.
    """
    api_slug = slugify(api_name)
    steps = config.steps
    status_map = config.jira_status_map

    # Determine mode: auto-detect fuzzy if labeled tickets are absent
    labeled_count = _count_labeled_tickets(api_slug, config, client)
    use_fuzzy = fuzzy or (labeled_count == 0 and epic_key is not None)

    if use_fuzzy and epic_key:
        epic_tickets = _fetch_epic_tickets(epic_key, config, client)
    else:
        epic_tickets = []

    checklist_steps: list[ChecklistStep] = []
    missing_artifacts: list[str] = []

    for step in steps:
        cs = _resolve_step(step, api_slug, config, client, status_map, use_fuzzy, epic_tickets)
        _evaluate_artifacts(cs, client)

        # Collect missing artifacts for required steps
        if not step.optional:
            for artifact in step.required_artifacts:
                if not cs.artifact_hits.get(artifact.kind, False):
                    missing_artifacts.append(
                        f"{step.name}: missing {artifact.kind}"
                        + (f"={artifact.value}" if artifact.value else "")
                    )

        checklist_steps.append(cs)

    required = [s for s in checklist_steps if not s.definition.optional]
    score = sum(1 for s in required if _step_satisfied(s))

    return AuditResult(
        api_name=api_name,
        epic_key=epic_key or "unknown",
        score=score,
        max_score=len(required),
        steps=checklist_steps,
        missing_artifacts=missing_artifacts,
        generated_at=datetime.now(timezone.utc).isoformat(),
        fuzzy_mode=use_fuzzy,
    )


def _count_labeled_tickets(api_slug: str, config: Config, client: JiraClient) -> int:
    jql = (
        f'project = "{config.jira.project}" AND labels = "api-checker" '
        f'AND labels = "api-{api_slug}"'
    )
    return len(client.search(jql, fields=["summary"], max_results=10))


def _fetch_epic_tickets(epic_key: str, config: Config, client: JiraClient) -> list[dict]:
    """Fetch all IGAV tickets under an epic."""
    jql = (
        f'project = "{config.jira.project}" AND '
        f'("Epic Link" = "{epic_key}" OR parent = "{epic_key}")'
    )
    return client.search(jql, fields=["summary", "status", "resolution", "assignee", "updated", "description", "labels"], max_results=200)


def _resolve_step(
    step,
    api_slug: str,
    config: Config,
    client: JiraClient,
    status_map: dict,
    use_fuzzy: bool,
    epic_tickets: list[dict],
) -> ChecklistStep:
    """Find the Jira ticket(s) for a step — strict or fuzzy."""

    # Always try strict label match first
    jql = step_jql(config.jira.project, step.id, api_slug)
    issues = client.search(jql, fields=["summary", "status", "resolution", "assignee", "updated", "description"], max_results=1)

    if issues:
        return _issue_to_step(issues[0], step, status_map, fuzzy_match=False)

    # Fuzzy fallback: keyword match against epic tickets
    if use_fuzzy and epic_tickets:
        matched = _fuzzy_match(step, epic_tickets)
        if matched:
            cs = _issue_to_step(matched, step, status_map, fuzzy_match=True)
            cs.evidence.append(f"Fuzzy match on keywords: {step.fuzzy_keywords[:3]}")
            return cs

    return ChecklistStep(definition=step, status="missing")


def _fuzzy_match(step, tickets: list[dict]) -> dict | None:
    """Find best-matching ticket for a step using keyword scoring."""
    keywords = [k.lower() for k in step.fuzzy_keywords]
    best_score = 0
    best_ticket = None

    for ticket in tickets:
        fields = ticket.get("fields", {})
        summary = (fields.get("summary") or "").lower()
        desc_text = _extract_text(fields.get("description", "")).lower()
        text = summary + " " + desc_text

        score = sum(1 for kw in keywords if kw in text)
        # Weight summary matches higher
        score += sum(2 for kw in keywords if kw in summary)

        if score > best_score:
            best_score = score
            best_ticket = ticket

    # Require at least one keyword match to count
    return best_ticket if best_score >= 1 else None


def _extract_text(desc) -> str:
    if isinstance(desc, str):
        return desc
    if isinstance(desc, dict):
        parts = []
        if desc.get("type") == "text":
            parts.append(desc.get("text", ""))
        for child in desc.get("content", []):
            parts.append(_extract_text(child))
        return " ".join(parts)
    return ""


def _issue_to_step(issue: dict, step, status_map: dict, fuzzy_match: bool) -> ChecklistStep:
    fields = issue.get("fields", {})
    jira_status = fields.get("status", {}).get("name", "")
    resolution = fields.get("resolution") or {}
    resolution_name = resolution.get("name") if isinstance(resolution, dict) else None
    assignee = fields.get("assignee") or {}
    assignee_name = assignee.get("displayName") if isinstance(assignee, dict) else None
    updated = fields.get("updated", "")

    mapped_status = status_map.get(jira_status, "in-progress")

    return ChecklistStep(
        definition=step,
        jira_key=issue["key"],
        status=mapped_status,
        assignee=assignee_name,
        resolution=resolution_name,
        summary=fields.get("summary", ""),
        updated=updated[:10] if updated else None,
        fuzzy_match=fuzzy_match,
    )


def _evaluate_artifacts(cs: ChecklistStep, client: JiraClient) -> None:
    """Check each required artifact and record hits."""
    for artifact in cs.definition.required_artifacts:
        hit = _check_artifact(cs, artifact, client)
        cs.artifact_hits[artifact.kind] = hit
        if hit:
            cs.evidence.append(f"✓ {artifact.kind}" + (f"={artifact.value}" if artifact.value else ""))


def _check_artifact(cs: ChecklistStep, artifact: RequiredArtifact, client: JiraClient) -> bool:
    if artifact.kind == "ticket_exists":
        return cs.jira_key is not None

    if artifact.kind == "jira_resolution":
        if cs.resolution is None:
            return False
        return cs.resolution.lower() == (artifact.value or "").lower() or cs.status == "done"

    if artifact.kind == "label_present":
        return True  # Labels already matched to get here; assume present if ticket found

    if artifact.kind == "confluence_link":
        if cs.jira_key is None:
            return False
        try:
            issue_data = client.get_issue(cs.jira_key)
            return client.has_confluence_link(issue_data)
        except Exception:
            return False

    return False


def _step_satisfied(cs: ChecklistStep) -> bool:
    """A step is satisfied when all its required artifacts are present."""
    return all(cs.artifact_hits.get(a.kind, False) for a in cs.definition.required_artifacts)
