"""Configuration loading and validation for api-checker."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .exceptions import ChecklistError, ConfigurationError
from .models import RequiredArtifact, StepDefinition

_DEFAULT_CHECKLIST = Path(__file__).parent / "checklist.yaml"
_USER_CHECKLIST = Path.home() / ".api-checker.yaml"

ALLOWED_ARTIFACT_KINDS = {"jira_resolution", "confluence_link", "label_present", "ticket_exists"}


@dataclass
class JiraConfig:
    base_url: str
    email: str
    token: str
    project: str
    parent_project: str
    epic_link_field: str


@dataclass
class Config:
    jira: JiraConfig
    jira_status_map: dict[str, str]
    steps: list[StepDefinition]


def load_config(path: Optional[str] = None) -> Config:
    """Load configuration from YAML, with env var credentials injected."""
    yaml_path = _resolve_yaml_path(path)
    raw = _load_yaml(yaml_path)
    _validate_yaml_structure(raw)

    email = _require_env("CONFLUENCE_EMAIL")
    token = _require_env("CONFLUENCE_API_TOKEN")
    base_url = _require_env("CONFLUENCE_BASE_URL").rstrip("/")

    jira_cfg = raw.get("jira", {})
    jira = JiraConfig(
        base_url=base_url,
        email=email,
        token=token,
        project=jira_cfg.get("project", "IGAV"),
        parent_project=jira_cfg.get("parent_project", "PM"),
        epic_link_field=jira_cfg.get("epic_link_field", "customfield_10014"),
    )

    steps = _parse_steps(raw["steps"])
    _validate_steps(steps)

    return Config(
        jira=jira,
        jira_status_map=raw.get("jira_status_map", {}),
        steps=steps,
    )


def _resolve_yaml_path(path: Optional[str]) -> Path:
    if path:
        p = Path(path)
        if not p.exists():
            raise ConfigurationError(f"Config file not found: {path}")
        return p
    if _USER_CHECKLIST.exists():
        return _USER_CHECKLIST
    return _DEFAULT_CHECKLIST


def _load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise ConfigurationError(
            f"Required environment variable '{name}' is not set.\n"
            "Set CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN, and CONFLUENCE_BASE_URL."
        )
    return val


def _validate_yaml_structure(raw: dict) -> None:
    if "steps" not in raw:
        raise ChecklistError("checklist.yaml must contain a 'steps' key.")
    if not isinstance(raw["steps"], list) or len(raw["steps"]) == 0:
        raise ChecklistError("checklist.yaml 'steps' must be a non-empty list.")


def _parse_steps(raw_steps: list[dict]) -> list[StepDefinition]:
    steps = []
    for s in raw_steps:
        artifacts = [
            RequiredArtifact(kind=a["kind"], value=a.get("value"))
            for a in s.get("required_artifacts", [])
        ]
        steps.append(StepDefinition(
            id=s["id"],
            order=s["order"],
            name=s["name"],
            issue_type=s.get("issue_type", "Story"),
            summary_template=s["summary_template"],
            description_template=s["description_template"],
            labels=s.get("labels", []),
            acceptance_criteria=s.get("acceptance_criteria", []),
            blocks=s.get("blocks", []),
            required_artifacts=artifacts,
            optional=s.get("optional", False),
            fuzzy_keywords=s.get("fuzzy_keywords", []),
        ))
    return sorted(steps, key=lambda x: x.order)


def _validate_steps(steps: list[StepDefinition]) -> None:
    ids = {s.id for s in steps}
    optional_count = sum(1 for s in steps if s.optional)

    if optional_count > 2:
        import warnings
        warnings.warn(
            f"{optional_count} steps marked optional — verify this is intentional.",
            stacklevel=3,
        )

    for step in steps:
        for blocked_id in step.blocks:
            if blocked_id not in ids:
                raise ChecklistError(
                    f"Step '{step.id}' blocks unknown step '{blocked_id}'."
                )
        for artifact in step.required_artifacts:
            if artifact.kind not in ALLOWED_ARTIFACT_KINDS:
                raise ChecklistError(
                    f"Step '{step.id}' has unknown artifact kind '{artifact.kind}'. "
                    f"Allowed: {sorted(ALLOWED_ARTIFACT_KINDS)}"
                )
