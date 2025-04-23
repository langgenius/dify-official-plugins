from collections.abc import Generator
from typing import Any

from atlassian.bitbucket import Cloud
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetWorkSpaceTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:

        bitbucket_url = self.runtime.credentials.get(
            "bitbucket_url", "https://api.bitbucket.org"
        )
        username = self.runtime.credentials.get("username")
        password = self.runtime.credentials.get("password")

        workspace_slug = tool_parameters.get("workspace_slug")

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

            projects = [project for project in workspace.projects.each()]

            yield self.create_json_message(
                {
                    "workspace": {
                        "name": workspace.name,
                        "slug": workspace.slug,
                        "uuid": workspace.uuid,
                        "is_private": workspace.is_private,
                        "created_on": workspace.created_on,
                        "updated_on": workspace.updated_on,
                        "projects": [
                            {
                                "name": project.name,
                                "key": project.key,
                                "description": project.description,
                                "is_private": project.is_private,
                                "created_on": project.created_on,
                                "updated_on": project.updated_on,
                            }
                            for project in projects  # type: Project
                        ],
                    }
                }
            )

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

        yield self.create_json_message({"result": "Hello, world!"})
