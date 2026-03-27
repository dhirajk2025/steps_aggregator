"""Data models for api-checker."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class RequiredArtifact:
    """Defines what evidence must exist for a step to be considered complete."""
    kind: str   # "jira_resolution" | "confluence_link" | "label_present" | "ticket_exists"
    value: Optional[str] = None


@dataclass(frozen=True)
class StepDefinition:
    """Immutable definition of a checklist step loaded from checklist.yaml."""
    id: str
    order: int
    name: str
    issue_type: str
    summary_template: str
    description_template: str
    labels: list[str]
    acceptance_criteria: list[str]
    blocks: list[str]
    required_artifacts: list[RequiredArtifact]
    optional: bool = False
    fuzzy_keywords: list[str] = field(default_factory=list)


@dataclass
class ChecklistStep:
    """Runtime state of a single checklist step for a specific API."""
    definition: StepDefinition
    jira_key: Optional[str] = None
    status: str = "missing"     # missing | todo | in-progress | done | blocked
    assignee: Optional[str] = None
    resolution: Optional[str] = None
    summary: Optional[str] = None
    updated: Optional[str] = None
    evidence: list[str] = field(default_factory=list)
    artifact_hits: dict[str, bool] = field(default_factory=dict)
    fuzzy_match: bool = False   # True if matched via keyword rather than label


@dataclass
class AuditResult:
    """Full compliance audit result for an API."""
    api_name: str
    epic_key: str
    score: int
    max_score: int
    steps: list[ChecklistStep]
    missing_artifacts: list[str]
    generated_at: str
    fuzzy_mode: bool = False

    @property
    def percent(self) -> int:
        if self.max_score == 0:
            return 0
        return round(self.score / self.max_score * 100)
