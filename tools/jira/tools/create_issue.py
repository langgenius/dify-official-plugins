from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import connect
from tools.jira_client import JiraAuthError
from tools.jira_fields import issue_fields

from utils.md2adf import markdown_to_adf

# Optional fields; only the ones given are sent.
OPTIONAL_FIELDS = ("assignee", "priority", "labels", "due_date", "parent_key", "custom_fields")


class CreateIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = yield from connect(self)
        if jira is None:
            return

        summary = tool_parameters.get("summary")
        project_key: str = str(tool_parameters.get("project_key") or "").strip()
        issue_type_id = tool_parameters.get("issue_type_id")
        description: str = tool_parameters.get("description")

        fields: dict[str, Any] = {
            "summary": summary,
            # The parameter takes a project ID (10001) or key (PROJ).
            "project": {"id": project_key} if project_key.isdigit() else {"key": project_key},
            "issuetype": {
                "id": issue_type_id,
            },
        }

        if description:
            fields["description"] = markdown_to_adf(description) if jira.cloud else description

        try:
            fields.update(
                issue_fields(SimpleNamespace(cloud=jira.cloud), {k: tool_parameters.get(k) for k in OPTIONAL_FIELDS})
            )
        except JiraAuthError as e:
            yield self.create_text_message(str(e))
            return

        yield self.create_json_message(
            jira.issue_create(
                fields=fields
            )
        )
