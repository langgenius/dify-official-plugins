from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.pipeline.service import ArtifactPayload, table_self_query


class TableCookingTool(Tool):
    """
    Invoke model:
    https://docs.dify.ai/zh-hans/plugins/schema-definition/reverse-invocation-of-the-dify-service/model#zui-jia-shi-jian
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        # Parameter verification
        ArtifactPayload.validation(tool_parameters)

        # Build artifact for QA
        artifact = ArtifactPayload.from_dify(tool_parameters)

        # Invoke tool-strategy
        try:
            result = table_self_query(artifact, self.session)
            yield self.create_json_message(result)
        finally:
            artifact.release_cache()
