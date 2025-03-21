import json
from collections.abc import Generator
from typing import Any
from urllib.parse import urlparse

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
        chef = tool_parameters.get("chef")

        logger.debug(json.dumps(chef, indent=2, ensure_ascii=False))

        # !!<LLM edit>
        if not query or not isinstance(query, str):
            raise ToolProviderCredentialValidationError("Query is required and must be a string.")
        if not table or not isinstance(table, File):
            raise ToolProviderCredentialValidationError("Table is required and must be a file.")
        if table.extension not in [".csv", ".xls", ".xlsx"]:
            raise ToolProviderCredentialValidationError("Table must be a csv, xls, or xlsx file.")

        # Check if the URL is of string type
        if not isinstance(table.url, str):
            raise ToolProviderCredentialValidationError("URL must be a string.")

        # Parses URL and verify scheme
        parsed_url = urlparse(table.url)
        if parsed_url.scheme not in ["http", "https"]:
            scheme = parsed_url.scheme or "missing"
            raise ToolProviderCredentialValidationError(
                f"Invalid URL scheme '{scheme}'. FILES_URL must start with 'http://' or 'https://'."
                f"Please check more details https://github.com/langgenius/dify/blob/72191f5b13c55b44bcd3b25f7480804259e53495/docker/.env.example#L42"
            )
        # !!</LLM edit>

        # Build artifact for QA
        artifact = ArtifactPayload.from_dify_tool_parameters(query, table, chef)
        logger.debug(artifact)

        try:
            print("1")
            result = table_self_query(artifact, self.session)
            print(result)
        finally:
            artifact.release_cache()

        yield self.create_json_message({"result": "Hello, world!"})
