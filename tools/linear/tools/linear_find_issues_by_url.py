import re
from typing import Any, Dict, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from client import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

ATTACHMENT_FIELDS = """
  id
  title
  subtitle
  url
  sourceType
  metadata
  createdAt
  issue {
    id
    identifier
    title
    description
    priority
    priorityLabel
    url
    createdAt
    updatedAt
    completedAt
    canceledAt
    dueDate
    state { id name type }
    assignee { id name email }
    team { id key name }
    project { id name }
    labels { nodes { id name } }
  }
"""

ATTACHMENTS_FOR_URL_QUERY = (
    """
query AttachmentsForURL($url: String!, $first: Int) {
  attachmentsForURL(url: $url, first: $first) {
    nodes {%s}
  }
}
"""
    % ATTACHMENT_FIELDS
)

ATTACHMENTS_CONTAINING_URL_QUERY = (
    """
query AttachmentsContainingURL($fragment: String!, $first: Int) {
  attachments(filter: { url: { containsIgnoreCase: $fragment } }, first: $first) {
    nodes {%s}
  }
}
"""
    % ATTACHMENT_FIELDS
)


def _parse_limit(value: Any) -> int:
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


def _contains_fragment(url: str, fragment: str) -> bool:
    """Match the fragment only when it is not followed by another alphanumeric character.

    This keeps `.../tickets/123` from matching `.../tickets/1234`.
    """
    return re.search(re.escape(fragment) + r"(?![0-9A-Za-z])", url or "", re.IGNORECASE) is not None


def group_attachments_by_issue(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues: dict[str, dict[str, Any]] = {}
    for attachment in attachments:
        issue = attachment.get("issue")
        if not issue or not issue.get("id"):
            continue
        entry = issues.get(issue["id"])
        if entry is None:
            labels = (issue.get("labels") or {}).get("nodes") or []
            entry = {**issue, "labels": labels, "attachments": []}
            issues[issue["id"]] = entry
        entry["attachments"].append({key: value for key, value in attachment.items() if key != "issue"})
    return list(issues.values())


class LinearFindIssuesByUrlTool(Tool):
    """Find Linear issues that have an attachment pointing to an external URL."""

    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        api_key = self.runtime.credentials.get("linear_api_key")
        if not api_key:
            yield self.create_text_message("Linear API Key is required.")
            return

        url = str(tool_parameters.get("url") or "").strip()
        if not url:
            yield self.create_text_message("Error: URL ('url') is required.")
            return

        match_mode = str(tool_parameters.get("match_mode") or "exact").strip().lower()
        if match_mode not in ("exact", "contains"):
            yield self.create_text_message("Error: match_mode must be 'exact' or 'contains'.")
            return
        limit = _parse_limit(tool_parameters.get("limit"))

        try:
            linear_client = Linear(api_key)
            if match_mode == "exact":
                attachments: list[dict[str, Any]] = []
                for candidate in dict.fromkeys([url, url.rstrip("/")]):
                    result = linear_client.query_graphql(
                        ATTACHMENTS_FOR_URL_QUERY, variables={"url": candidate, "first": limit}
                    )
                    attachments = ((result.get("data") or {}).get("attachmentsForURL") or {}).get("nodes") or []
                    if attachments:
                        break
            else:
                result = linear_client.query_graphql(
                    ATTACHMENTS_CONTAINING_URL_QUERY, variables={"fragment": url, "first": limit}
                )
                attachments = ((result.get("data") or {}).get("attachments") or {}).get("nodes") or []
                attachments = [item for item in attachments if _contains_fragment(item.get("url"), url)]

            issues = group_attachments_by_issue(attachments)
            yield self.create_json_message(
                {"url": url, "match_mode": match_mode, "count": len(issues), "issues": issues}
            )
        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"An unexpected error occurred: {str(e)}")
