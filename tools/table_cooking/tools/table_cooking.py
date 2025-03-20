from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.file.file import File
from loguru import logger

from tools.pipeline.service import ArtifactPayload, table_self_query


class TableCookingTool(Tool):
    """
    Invoke model:
    https://docs.dify.ai/zh-hans/plugins/schema-definition/reverse-invocation-of-the-dify-service/model#zui-jia-shi-jian
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        query = tool_parameters.get("query", "")
        table = tool_parameters.get("table")
        chef = tool_parameters.get("chef", "")

        logger.debug(tool_parameters)

        if not query or not isinstance(query, str):
            raise ToolProviderCredentialValidationError("Query is required and must be a string.")
        if not table or not isinstance(table, File):
            raise ToolProviderCredentialValidationError("Table is required and must be a file.")
        if table.extension not in [".csv", ".xls", ".xlsx"]:
            raise ToolProviderCredentialValidationError("Table must be a csv, xls, or xlsx file.")

        # Build artifact for QA
        artifact = ArtifactPayload.from_dify_file(query, table)
        logger.debug(artifact)

        try:
            # result = table_self_query(artifact)
            response = self.session.model.llm.invoke(
                model_config=chef, prompt_messages=[], stream=False
            )
            print(response)
            # print(result)
        finally:
            artifact.release_cache()

        yield self.create_json_message({"result": "Hello, world!"})
