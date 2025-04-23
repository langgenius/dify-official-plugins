from collections.abc import Generator
from typing import Any

from atlassian.bitbucket import Cloud
from atlassian.bitbucket.cloud.workspaces import Workspace
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListWorkSpaceTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        bitbucket_url = self.runtime.credentials.get(
            "bitbucket_url", "https://api.bitbucket.org"
        )
        username = self.runtime.credentials.get("username")
        password = self.runtime.credentials.get("password")

        try:
            bitbucket = Cloud(
                url=bitbucket_url,
                username=username,
                password=password,
            )

            workspaces: list[Workspace] = [
                workspace for workspace in bitbucket.workspaces.each()
            ]

            yield self.create_json_message(
                {
                    "workspaces": [
                        {
                            "name": workspace.name,
                            "slug": workspace.slug,
                            "uuid": workspace.uuid,
                            "is_private": workspace.is_private,
                            "created_on": workspace.created_on,
                            "updated_on": workspace.updated_on,
                        }
                        for workspace in workspaces
                    ]
                }
            )

        except Exception as e:
            yield self.create_text_message(f"Failed to connect to Bitbucket: {str(e)}")
            return

        yield self.create_json_message({"result": "Hello, world!"})
