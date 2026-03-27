"""Output rendering: Rich terminal, JSON, Markdown."""

from __future__ import annotations

import json
from typing import Union

from rich.console import Console
from rich.table import Table
from rich import box
from rich.text import Text
from rich.panel import Panel

from .models import AuditResult, ChecklistStep
from .plan import PlanResult

console = Console()
err_console = Console(stderr=True)

STATUS_STYLES = {
    "done":       ("✓", "green"),
    "in-progress":("~", "yellow"),
    "todo":       ("○", "default"),
    "blocked":    ("✗", "red"),
    "missing":    ("✗", "bright_red"),
    "created":    ("✓", "green"),
    "skipped":    ("→", "dim"),
    "dry-run":    ("~", "cyan"),
}


# ── Plan output ───────────────────────────────────────────────────────────────

def render_plan(result: PlanResult, api_name: str, dry_run: bool, fmt: str = "terminal") -> str:
    if fmt == "json":
        return _plan_json(result, api_name, dry_run)
    if fmt == "markdown":
        return _plan_markdown(result, api_name, dry_run)
    _plan_rich(result, api_name, dry_run)
    return ""


def _plan_rich(result: PlanResult, api_name: str, dry_run: bool) -> None:
    prefix = "[DRY RUN] " if dry_run else ""

    # Epic summary line
    if result.epic_key:
        epic_action = "Created epic" if result.epic_created else "Reusing epic"
        console.print(f"[bold]{prefix}{epic_action}:[/bold] [cyan]{result.epic_key}[/cyan] — {api_name}")
    else:
        console.print(f"[bold]{prefix}Epic:[/bold] [dim](would create)[/dim] — {api_name}")

    table = Table(box=box.ROUNDED, show_lines=False, show_header=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Step", min_width=30)
    table.add_column("Status", width=10)
    table.add_column("Ticket", width=12)
    table.add_column("Notes")

    for cs in result.steps:
        icon, style = STATUS_STYLES.get(cs.status, ("?", "default"))
        status_text = Text(f"{icon} {cs.status}", style=style)
        ticket = cs.jira_key or "—"
        note = cs.evidence[0] if cs.evidence else ""
        table.add_row(
            str(cs.definition.order),
            cs.definition.name,
            status_text,
            ticket,
            note,
        )
    console.print(table)


def _plan_json(result: PlanResult, api_name: str, dry_run: bool) -> str:
    return json.dumps({
        "api_name": api_name,
        "dry_run": dry_run,
        "epic_key": result.epic_key,
        "epic_created": result.epic_created,
        "steps": [
            {
                "step_id": cs.definition.id,
                "order": cs.definition.order,
                "name": cs.definition.name,
                "status": cs.status,
                "jira_key": cs.jira_key,
                "notes": cs.evidence,
            }
            for cs in result.steps
        ],
    }, indent=2)


def _plan_markdown(result: PlanResult, api_name: str, dry_run: bool) -> str:
    lines = [f"## API Checker Plan: {api_name}", ""]
    if dry_run:
        lines.append("> **Dry run** — no tickets were created.\n")
    if result.epic_key:
        action = "Created" if result.epic_created else "Reusing"
        lines.append(f"**Epic:** `{result.epic_key}` ({action})\n")
    lines.append("| # | Step | Status | Ticket |")
    lines.append("|---|------|--------|--------|")
    for cs in result.steps:
        ticket = f"`{cs.jira_key}`" if cs.jira_key else "—"
        lines.append(f"| {cs.definition.order} | {cs.definition.name} | {cs.status} | {ticket} |")
    return "\n".join(lines)


# ── Status output ─────────────────────────────────────────────────────────────

def render_status(steps: list[ChecklistStep], api_name: str, fmt: str = "terminal") -> str:
    if fmt == "json":
        return _status_json(steps, api_name)
    if fmt == "markdown":
        return _status_markdown(steps, api_name)
    _status_rich(steps, api_name)
    return ""


def _status_rich(steps: list[ChecklistStep], api_name: str) -> None:
    table = Table(title=f"Status: {api_name}", box=box.ROUNDED)
    table.add_column("#", style="dim", width=3)
    table.add_column("Step", min_width=30)
    table.add_column("Status", width=14)
    table.add_column("Ticket", width=12)
    table.add_column("Assignee", width=20)
    table.add_column("Updated", width=12)

    for cs in steps:
        icon, style = STATUS_STYLES.get(cs.status, ("?", "default"))
        status_text = Text(f"{icon} {cs.status}", style=style)
        table.add_row(
            str(cs.definition.order),
            cs.definition.name,
            status_text,
            cs.jira_key or "—",
            cs.assignee or "—",
            cs.updated or "—",
        )
    console.print(table)


def _status_json(steps: list[ChecklistStep], api_name: str) -> str:
    return json.dumps({
        "api_name": api_name,
        "steps": [
            {
                "step_id": cs.definition.id,
                "order": cs.definition.order,
                "name": cs.definition.name,
                "status": cs.status,
                "jira_key": cs.jira_key,
                "assignee": cs.assignee,
                "updated": cs.updated,
            }
            for cs in steps
        ],
    }, indent=2)


def _status_markdown(steps: list[ChecklistStep], api_name: str) -> str:
    lines = [f"## Status: {api_name}", ""]
    lines.append("| # | Step | Status | Ticket | Assignee |")
    lines.append("|---|------|--------|--------|----------|")
    for cs in steps:
        icon, _ = STATUS_STYLES.get(cs.status, ("?", "default"))
        ticket = f"`{cs.jira_key}`" if cs.jira_key else "—"
        lines.append(f"| {cs.definition.order} | {cs.definition.name} | {icon} {cs.status} | {ticket} | {cs.assignee or '—'} |")
    return "\n".join(lines)


# ── Audit output ──────────────────────────────────────────────────────────────

def render_audit(result: AuditResult, fmt: str = "terminal", verbose: bool = False) -> str:
    if fmt == "json":
        return _audit_json(result)
    if fmt == "markdown":
        return _audit_markdown(result, verbose)
    _audit_rich(result, verbose)
    return ""


def _audit_rich(result: AuditResult, verbose: bool) -> None:
    pct = result.percent
    score_color = "green" if pct >= 80 else ("yellow" if pct >= 50 else "red")
    score_str = f"[{score_color}]{result.score}/{result.max_score} steps complete ({pct}%)[/{score_color}]"
    mode_str = " [dim](fuzzy mode)[/dim]" if result.fuzzy_mode else ""

    console.print(Panel(
        f"[bold]{result.api_name}[/bold]{mode_str}\n{score_str}",
        title="Audit Report",
        border_style=score_color,
    ))

    table = Table(box=box.ROUNDED, show_lines=False)
    table.add_column("#", style="dim", width=3)
    table.add_column("Step", min_width=30)
    table.add_column("Status", width=14)
    table.add_column("Ticket", width=12)
    table.add_column("Score", width=7)
    if verbose:
        table.add_column("Evidence")

    for cs in result.steps:
        from .audit import _step_satisfied
        satisfied = _step_satisfied(cs)
        icon, style = STATUS_STYLES.get(cs.status, ("?", "default"))
        score_icon = Text("✓", style="green") if satisfied else Text("✗", style="red")
        if cs.definition.optional:
            score_icon = Text("opt", style="dim")
        row = [
            str(cs.definition.order),
            cs.definition.name + (" [dim](fuzzy)[/dim]" if cs.fuzzy_match else ""),
            Text(f"{icon} {cs.status}", style=style),
            cs.jira_key or "—",
            score_icon,
        ]
        if verbose:
            row.append("; ".join(cs.evidence) or "—")
        table.add_row(*row)

    console.print(table)

    if result.missing_artifacts:
        console.print("\n[bold red]Missing artifacts:[/bold red]")
        for m in result.missing_artifacts:
            console.print(f"  [red]✗[/red] {m}")


def _audit_json(result: AuditResult) -> str:
    from .audit import _step_satisfied
    return json.dumps({
        "api_name": result.api_name,
        "epic_key": result.epic_key,
        "score": result.score,
        "max_score": result.max_score,
        "percent": result.percent,
        "fuzzy_mode": result.fuzzy_mode,
        "generated_at": result.generated_at,
        "steps": [
            {
                "step_id": cs.definition.id,
                "order": cs.definition.order,
                "name": cs.definition.name,
                "status": cs.status,
                "jira_key": cs.jira_key,
                "satisfied": _step_satisfied(cs),
                "fuzzy_match": cs.fuzzy_match,
                "evidence": cs.evidence,
                "missing_artifacts": [
                    a.kind for a in cs.definition.required_artifacts
                    if not cs.artifact_hits.get(a.kind, False)
                ],
            }
            for cs in result.steps
        ],
        "missing_artifacts": result.missing_artifacts,
    }, indent=2)


def _audit_markdown(result: AuditResult, verbose: bool) -> str:
    from .audit import _step_satisfied
    pct = result.percent
    lines = [
        f"## Audit Report: {result.api_name}",
        "",
        f"**Score:** {result.score}/{result.max_score} ({pct}%)"
        + (" _(fuzzy mode)_" if result.fuzzy_mode else ""),
        f"**Generated:** {result.generated_at[:19]}",
        "",
        "| # | Step | Status | Ticket | Pass |",
        "|---|------|--------|--------|------|",
    ]
    for cs in result.steps:
        satisfied = _step_satisfied(cs)
        icon, _ = STATUS_STYLES.get(cs.status, ("?", "default"))
        ticket = f"`{cs.jira_key}`" if cs.jira_key else "—"
        pass_icon = "✓" if satisfied else ("opt" if cs.definition.optional else "✗")
        fuzzy = " _(fuzzy)_" if cs.fuzzy_match else ""
        lines.append(f"| {cs.definition.order} | {cs.definition.name}{fuzzy} | {icon} {cs.status} | {ticket} | {pass_icon} |")

    if result.missing_artifacts:
        lines += ["", "### Missing Artifacts", ""]
        for m in result.missing_artifacts:
            lines.append(f"- ✗ {m}")

    return "\n".join(lines)
