import json
from collections.abc import Generator
from typing import Any
from urllib.parse import urlparse

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.file.file import File

from tools.pipeline.service import ArtifactPayload, table_self_query


class TableCookingTool(Tool):
    """
    Invoke model:
    https://docs.dify.ai/zh-hans/plugins/schema-definition/reverse-invocation-of-the-dify-service/model#zui-jia-shi-jian
    """

    @staticmethod
    def _validation(tool_parameters: dict[str, Any]):
        query = tool_parameters.get("query")
        table = tool_parameters.get("table")
        chef = tool_parameters.get("chef")

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

        # Prevent stupidity
        not_available_models = [
            "gpt-4.5-preview",
            "gpt-4.5-preview-2025-02-27",
            "o1",
            "o1-2024-12-17",
            "o1-pro",
            "o1-pro-2025-03-19",
        ]
        if (
            isinstance(chef, dict)
            and chef.get("model_type", "") == "llm"
            and chef.get("provider", "") == "langgenius/openai/openai"
            and chef.get("mode", "") == "chat"
        ):
            if use_model := chef.get("model"):
                if use_model in not_available_models:
                    raise ToolProviderCredentialValidationError(
                        f"Model `{use_model}` is not available for this tool. "
                        f"Please replace other cheaper models."
                    )

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        query = tool_parameters.get("query", "")
        table = tool_parameters.get("table")
        chef = tool_parameters.get("chef")

        self._validation(tool_parameters)

        # Build artifact for QA
        artifact = ArtifactPayload.from_dify_tool_parameters(query, table, chef)

        try:
            result = table_self_query(artifact, self.session)
        finally:
            artifact.release_cache()

        yield self.create_json_message(result)
