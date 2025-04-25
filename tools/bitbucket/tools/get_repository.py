from collections.abc import Generator
from typing import Any

from atlassian.bitbucket import Cloud
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetRepositoryTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        bitbucket_url = self.runtime.credentials.get(
            "bitbucket_url", "https://api.bitbucket.org"
        )
        username = self.runtime.credentials.get("username")
        password = self.runtime.credentials.get("password")

        workspace_slug = tool_parameters.get("workspace_slug")
        repositoriy_slug = tool_parameters.get("repository_slug")

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

            repositoriy = workspace.repositories.get(repository=repositoriy_slug)
            if not repositoriy:
                yield self.create_text_message(
                    f"Repository {repositoriy_slug} not found."
                )
                return

            yield self.create_json_message(
                {
                    "name": repositoriy.name,
                    "slug": repositoriy.slug,
                    "uuid": repositoriy.uuid,
                    "is_private": repositoriy.is_private,
                    "created_on": repositoriy.created_on,
                    "updated_on": repositoriy.updated_on,
                    "description": repositoriy.description,
                }
            )

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_json_message({"result": "Hello, world!"})
