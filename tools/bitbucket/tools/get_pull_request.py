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

            yield self.create_json_message(
                {
                    "pull_requests": {
                        "id": pull_request.id,
                        "title": pull_request.title,
                        "description": pull_request.description,
                        "author": (
                            pull_request.author.display_name
                            if pull_request.author
                            else None
                        ),
                        "created_on": (
                            str(pull_request.created_on)
                            if pull_request.created_on
                            else None
                        ),
                        "updated_on": (
                            str(pull_request.updated_on)
                            if pull_request.updated_on
                            else None
                        ),
                        "source_branch": pull_request.source_branch,
                        "destination_branch": pull_request.destination_branch,
                        "comment_count": pull_request.comment_count,
                        "task_count": pull_request.task_count,
                        "is_merged": pull_request.is_merged,
                        "is_declined": pull_request.is_declined,
                        "diff": pull_request.diff(),
                    }
                }
            )

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
