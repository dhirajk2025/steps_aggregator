"""Exception hierarchy for api-checker."""


class ApiCheckerError(Exception):
    """Base exception for all api-checker errors."""


class ConfigurationError(ApiCheckerError):
    """Raised when required configuration or env vars are missing."""


class JiraError(ApiCheckerError):
    """Raised when a Jira API call fails."""


class JiraNotFoundError(JiraError):
    """Raised when a Jira issue or epic is not found."""


class ChecklistError(ApiCheckerError):
    """Raised when checklist.yaml is invalid."""
