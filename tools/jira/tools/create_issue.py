from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # Get credentials
            jira_url = self.runtime.credentials.get("jira_url")
            username = self.runtime.credentials.get("username")
            api_token = self.runtime.credentials.get("api_token")

            if not all([jira_url, username, api_token]):
                yield self.create_text_message("Missing required Jira credentials. Please check your configuration.")
                return

            # Get and validate parameters
            summary = tool_parameters.get("summary")
            project_key = tool_parameters.get("project_key")
            issue_type_id = tool_parameters.get("issue_type_id")

            if not summary:
                yield self.create_text_message("Summary is required for creating a Jira issue.")
                return

            if not project_key:
                yield self.create_text_message("Project key is required for creating a Jira issue.")
                return

            # Initialize Jira client
            jira = Jira(
                url=jira_url,
                username=username,
                password=api_token,
            )

            # Prepare fields for issue creation
            fields = {
                "summary": summary,
                "project": {
                    "key": project_key,  # Changed from 'id' to 'key'
                }
            }

            # Add issue type if provided
            if issue_type_id:
                fields["issuetype"] = {"id": issue_type_id}

            # Create the issue
            try:
                result = jira.issue_create(fields=fields)
                yield self.create_text_message(f"Successfully created Jira issue: {result.get('key', 'Unknown')}")
                yield self.create_json_message(result)
            except Exception as e:
                error_message = str(e)
                if "Could not find project" in error_message:
                    yield self.create_text_message(f"Project '{project_key}' not found. Please check the project key.")
                elif "Could not find issue type" in error_message:
                    yield self.create_text_message(f"Issue type ID '{issue_type_id}' not found. Please check the issue type ID.")
                else:
                    yield self.create_text_message(f"Error creating Jira issue: {error_message}")

        except Exception as e:
            yield self.create_text_message(f"Unexpected error: {str(e)}")
