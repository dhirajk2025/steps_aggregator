"""CLI entry point for api-checker."""

from __future__ import annotations

import sys
from typing import Optional

import click

from . import __version__
from .config import load_config
from .exceptions import ApiCheckerError
from .jira_client import JiraClient
from . import audit as audit_mod
from . import plan as plan_mod
from . import status as status_mod
from . import renderer


def _output_fmt(json_flag: bool, markdown_flag: bool) -> str:
    if json_flag:
        return "json"
    if markdown_flag:
        return "markdown"
    return "terminal"


@click.group()
@click.version_option(__version__, prog_name="api-checker")
@click.option("--config", "config_path", default=None, metavar="PATH",
              help="Path to a YAML config override (default: ~/.api-checker.yaml or bundled checklist.yaml).")
@click.pass_context
def main(ctx: click.Context, config_path: Optional[str]) -> None:
    """API development compliance checker for ID.me engineering.

    Plan Jira tickets, track progress, and audit delivered APIs
    against the 7-step API development checklist.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


# ── plan ──────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("api_name")
@click.option("--epic", required=True, metavar="KEY",
              help="Parent epic key (e.g. PM-1313).")
@click.option("--step", "step_ids", multiple=True, metavar="STEP_ID",
              help="Create only specific steps (e.g. --step step-2-arb). Repeatable.")
@click.option("--dry-run", is_flag=True, default=False,
              help="Print what would be created without making Jira calls.")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output JSON.")
@click.option("--markdown", "markdown_flag", is_flag=True, default=False, help="Output Markdown.")
@click.pass_context
def plan(
    ctx: click.Context,
    api_name: str,
    epic: str,
    step_ids: tuple[str, ...],
    dry_run: bool,
    json_flag: bool,
    markdown_flag: bool,
) -> None:
    """Create Jira tickets for each checklist step.

    API_NAME is the name of the API being developed (e.g. "Face API").

    Example:
      api-checker plan "Face API" --epic PM-1313
    """
    try:
        config = load_config(ctx.obj.get("config_path"))
        client = JiraClient(config.jira)
        steps = plan_mod.run(
            api_name=api_name,
            epic_key=epic,
            config=config,
            client=client,
            step_ids=list(step_ids) if step_ids else None,
            dry_run=dry_run,
        )
        fmt = _output_fmt(json_flag, markdown_flag)
        out = renderer.render_plan(steps, api_name, dry_run, fmt)
        if out:
            click.echo(out)
    except ApiCheckerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)


# ── status ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("api_name")
@click.option("--epic", "epic_key", default=None, metavar="KEY",
              help="Filter by parent epic key (e.g. PM-1313 or IGAV-42).")
@click.option("--verbose", is_flag=True, default=False,
              help="Show ticket summaries and assignees.")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output JSON.")
@click.option("--markdown", "markdown_flag", is_flag=True, default=False, help="Output Markdown.")
@click.pass_context
def status(
    ctx: click.Context,
    api_name: str,
    epic_key: Optional[str],
    verbose: bool,
    json_flag: bool,
    markdown_flag: bool,
) -> None:
    """Show live checklist progress for an API.

    API_NAME is the name of the API (e.g. "Face API").

    Example:
      api-checker status "Face API"
      api-checker status "Face API" --epic PM-1313
    """
    try:
        config = load_config(ctx.obj.get("config_path"))
        client = JiraClient(config.jira)
        steps = status_mod.run(
            api_name=api_name,
            config=config,
            client=client,
            epic_key=epic_key,
            verbose=verbose,
        )
        fmt = _output_fmt(json_flag, markdown_flag)
        out = renderer.render_status(steps, api_name, fmt)
        if out:
            click.echo(out)
    except ApiCheckerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)


# ── audit ─────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("api_name")
@click.option("--epic", "epic_key", default=None, metavar="KEY",
              help="Parent epic key — required for fuzzy mode (e.g. PM-1313).")
@click.option("--fuzzy", is_flag=True, default=False,
              help="Use keyword-based ticket matching for APIs not planned with api-checker.")
@click.option("--fail-under", "fail_under", default=None, type=int, metavar="N",
              help="Exit with code 1 if compliance score is below N (useful for CI).")
@click.option("--verbose", is_flag=True, default=False,
              help="Show per-step evidence in the report.")
@click.option("--json", "json_flag", is_flag=True, default=False, help="Output JSON.")
@click.option("--markdown", "markdown_flag", is_flag=True, default=False, help="Output Markdown.")
@click.pass_context
def audit(
    ctx: click.Context,
    api_name: str,
    epic_key: Optional[str],
    fuzzy: bool,
    fail_under: Optional[int],
    verbose: bool,
    json_flag: bool,
    markdown_flag: bool,
) -> None:
    """Produce a compliance audit report for an API.

    API_NAME is the name of the API (e.g. "Face API").

    Fuzzy mode is automatically enabled for APIs that were not
    planned with api-checker (no api-checker labels found).

    Example:
      api-checker audit "Face API" --epic PM-1313
      api-checker audit "Face API" --epic PM-1313 --fuzzy --verbose
      api-checker audit "Face API" --epic PM-1313 --fail-under 5 --json
    """
    try:
        config = load_config(ctx.obj.get("config_path"))
        client = JiraClient(config.jira)
        result = audit_mod.run(
            api_name=api_name,
            config=config,
            client=client,
            epic_key=epic_key,
            fuzzy=fuzzy,
        )
        fmt = _output_fmt(json_flag, markdown_flag)
        out = renderer.render_audit(result, fmt, verbose)
        if out:
            click.echo(out)

        if fail_under is not None and result.score < fail_under:
            sys.exit(1)
    except ApiCheckerError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)
