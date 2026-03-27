"""Thin Jira REST API v3 wrapper."""

from __future__ import annotations

import os
import warnings
from typing import Any, Optional

import requests
from requests.auth import HTTPBasicAuth

from .config import JiraConfig
from .exceptions import JiraError, JiraNotFoundError

CONFLUENCE_DOMAIN = "atlassian.net/wiki"


def _ssl_verify() -> Any:
    """Resolve SSL verify setting from environment."""
    if os.environ.get("REQUESTS_CA_BUNDLE"):
        return os.environ["REQUESTS_CA_BUNDLE"]
    if os.environ.get("API_CHECKER_INSECURE", "").lower() in ("1", "true", "yes"):
        warnings.warn("SSL verification disabled via API_CHECKER_INSECURE", stacklevel=3)
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return False
    return True


class JiraClient:
    def __init__(self, cfg: JiraConfig) -> None:
        self._base = cfg.base_url.rstrip("/")
        self._auth = HTTPBasicAuth(cfg.email, cfg.token)
        self._project = cfg.project
        self._epic_link_field = cfg.epic_link_field
        self._verify = _ssl_verify()
        self._session = requests.Session()
        self._session.auth = self._auth
        self._session.verify = self._verify
        self._session.headers.update({"Accept": "application/json", "Content-Type": "application/json"})

    # ── Public API ────────────────────────────────────────────────────────────

    def get_issue(self, key: str) -> dict:
        """Fetch a single issue by key."""
        resp = self._get(f"/rest/api/3/issue/{key}")
        if resp.status_code == 404:
            raise JiraNotFoundError(f"Issue '{key}' not found.")
        self._raise(resp)
        return resp.json()

    def search(self, jql: str, fields: Optional[list[str]] = None, max_results: int = 100) -> list[dict]:
        """Paginated JQL search. Returns list of issue dicts."""
        if fields is None:
            fields = ["summary", "status", "resolution", "assignee", "labels", "updated", "description"]
        issues = []
        start = 0
        while True:
            params = {
                "jql": jql,
                "startAt": start,
                "maxResults": min(max_results, 100),
                "fields": ",".join(fields),
            }
            resp = self._get_params("/rest/api/3/search/jql", params)
            self._raise(resp)
            data = resp.json()
            batch = data.get("issues", [])
            issues.extend(batch)
            start += len(batch)
            if start >= data.get("total", 0) or not batch:
                break
            if len(issues) >= max_results:
                break
        return issues

    def create_issue(self, payload: dict) -> str:
        """Create an issue and return its key."""
        resp = self._post("/rest/api/3/issue", payload)
        if resp.status_code not in (200, 201):
            raise JiraError(f"Failed to create issue: {resp.status_code} {resp.text}")
        return resp.json()["key"]

    def create_link(self, inward_key: str, outward_key: str, link_type: str = "Blocks") -> None:
        """Create an issue link (inward_key blocks outward_key)."""
        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_key},
            "outwardIssue": {"key": outward_key},
        }
        resp = self._post("/rest/api/3/issueLink", payload)
        if resp.status_code not in (200, 201):
            raise JiraError(f"Failed to create link {inward_key}→{outward_key}: {resp.status_code} {resp.text}")

    def get_remote_links(self, key: str) -> list[dict]:
        """Get remote links (URLs) attached to an issue."""
        resp = self._get(f"/rest/api/3/issue/{key}/remotelink")
        if resp.status_code == 404:
            return []
        self._raise(resp)
        return resp.json()

    def get_issue_type_meta(self, project: str) -> dict:
        """Discover available fields for a project's issue types."""
        resp = self._get(f"/rest/api/3/issue/createmeta?projectKeys={project}&expand=projects.issuetypes.fields")
        self._raise(resp)
        return resp.json()

    def build_issue_payload(
        self,
        project: str,
        summary: str,
        description: str,
        issue_type: str,
        labels: list[str],
        epic_key: Optional[str] = None,
        epic_link_field: Optional[str] = None,
        priority: str = "Medium",
    ) -> dict:
        """Build a Jira issue creation payload."""
        fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "description": self._text_to_adf(description),
            "issuetype": {"name": issue_type},
            "labels": labels,
            "priority": {"name": priority},
        }
        if epic_key and epic_link_field:
            fields[epic_link_field] = epic_key
        return {"fields": fields}

    def has_confluence_link(self, issue: dict) -> bool:
        """Check if an issue's description or remote links contain a Confluence URL."""
        desc = self._extract_description_text(issue)
        if CONFLUENCE_DOMAIN in desc:
            return True
        key = issue.get("key", "")
        if key:
            try:
                remote = self.get_remote_links(key)
                for link in remote:
                    url = link.get("object", {}).get("url", "")
                    if CONFLUENCE_DOMAIN in url:
                        return True
            except JiraError:
                pass
        return False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, path: str) -> requests.Response:
        return self._session.get(f"{self._base}{path}", timeout=30)

    def _get_params(self, path: str, params: dict) -> requests.Response:
        return self._session.get(f"{self._base}{path}", params=params, timeout=30)

    def _post(self, path: str, payload: dict) -> requests.Response:
        return self._session.post(f"{self._base}{path}", json=payload, timeout=30)

    def _raise(self, resp: requests.Response) -> None:
        if not resp.ok:
            raise JiraError(f"Jira API error {resp.status_code}: {resp.text[:500]}")

    def _extract_description_text(self, issue: dict) -> str:
        """Recursively extract plain text from ADF description or return raw string."""
        desc = issue.get("fields", {}).get("description", "")
        if isinstance(desc, str):
            return desc
        if isinstance(desc, dict):
            return self._adf_to_text(desc)
        return ""

    def _adf_to_text(self, node: dict) -> str:
        """Flatten an ADF node tree to plain text."""
        parts = []
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        for child in node.get("content", []):
            parts.append(self._adf_to_text(child))
        return " ".join(parts)

    def _text_to_adf(self, text: str) -> dict:
        """Convert plain markdown-ish text to minimal ADF (paragraph per line)."""
        paragraphs = []
        for line in text.strip().splitlines():
            paragraphs.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line or " "}],
            })
        return {
            "type": "doc",
            "version": 1,
            "content": paragraphs or [{"type": "paragraph", "content": [{"type": "text", "text": " "}]}],
        }
