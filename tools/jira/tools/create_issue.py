from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.auth import auth

from utils.md2adf import markdown_to_adf


class CreateIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        jira = auth(self.runtime.credentials)

        summary = tool_parameters.get("summary")
        project_key: str = tool_parameters.get("project_key")
        issue_type_id = tool_parameters.get("issue_type_id")
        description: str = tool_parameters.get("description")

        fields: dict[str, Any] = {
            "summary": summary,
            "project": {
                "id": project_key,
            },
            "issuetype": {
                "id": issue_type_id,
            },
        }

        if description:
            fields["description"] = markdown_to_adf(description)

        yield self.create_json_message(
            jira.issue_create(
                fields=fields
            )
        )
