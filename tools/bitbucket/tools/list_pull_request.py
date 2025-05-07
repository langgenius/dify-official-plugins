from collections.abc import Generator
from typing import Any

from atlassian.bitbucket import Cloud
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListPullRequestTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        bitbucket_url = self.runtime.credentials.get(
            "bitbucket_url", "https://api.bitbucket.org"
        )
        username = self.runtime.credentials.get("username")
        password = self.runtime.credentials.get("password")

        workspace_slug = tool_parameters.get("workspace_slug")
        repository_slug = tool_parameters.get("repository_slug")

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

            pull_requests = repository.pullrequests.each()
            result = []
            for pr in pull_requests:
                # Extract information using properties from the PullRequest class
                result.append(
                    {
                        "id": pr.id,
                        "title": pr.title,
                        "description": pr.description,
                        "author": pr.author.display_name if pr.author else None,
                        "created_on": str(pr.created_on) if pr.created_on else None,
                        "updated_on": str(pr.updated_on) if pr.updated_on else None,
                        "source_branch": pr.source_branch,
                        "destination_branch": pr.destination_branch,
                        "comment_count": pr.comment_count,
                        "task_count": pr.task_count,
                        "is_merged": pr.is_merged,
                        "is_declined": pr.is_declined,
                    }
                )

            yield self.create_json_message({"pull_requests": result})

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
