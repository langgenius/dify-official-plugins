from collections.abc import Generator
from typing import Any

from atlassian.bitbucket import Cloud
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetPullRequestTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        bitbucket_url = self.runtime.credentials.get(
            "bitbucket_url", "https://api.bitbucket.org"
        )
        username = self.runtime.credentials.get("username")
        password = self.runtime.credentials.get("password")

        workspace_slug = tool_parameters.get("workspace_slug")
        repository_slug = tool_parameters.get("repository_slug")
        pull_request_id = tool_parameters.get("pull_request_id")
        comment = tool_parameters.get("comment")

        try:
            bitbucket = Cloud(
                url=bitbucket_url,
                username=username,
                password=password,
            )

            workspace = bitbucket.workspaces.get(workspace=workspace_slug)

            if not workspace:
                yield self.create_text_message(f"Workspace {workspace_slug} not found.")
                return

            repository = workspace.repositories.get(
                repository_slug,
            )
            if not repository:
                yield self.create_text_message(
                    f"Repository {repository_slug} not found in workspace {workspace_slug}."
                )
                return

            pull_request = repository.pullrequests.get(pull_request_id)
            if not pull_request:
                yield self.create_text_message(
                    f"Pull request {pull_request_id} not found in repository {repository_slug}."
                )
                return

            yield self.create_json_message(pull_request.comment(comment))

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
