from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GiteeAIToolEmbedding(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        headers = {"Content-Type": "application/json"}
        api_key = self.runtime.credentials.get("api_key")
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"

        payload: dict[str, Any] = {
            "model": tool_parameters.get("model", "Qwen3-Embedding-0.6B"),
            "input": tool_parameters.get("inputs"),
        }

        if payload["input"] in (None, ""):
            yield self.create_text_message("Input text is required to generate embeddings.")
            return

        optional_params = ("encoding_format", "dimensions", "user")
        for param in optional_params:
            if param in tool_parameters and tool_parameters[param] is not None:
                payload[param] = tool_parameters[param]

        response = requests.post("https://ai.gitee.com/v1/embeddings", json=payload, headers=headers)
        if response.status_code != 200:
            yield self.create_text_message(f"Got Error Response:{response.text}")
            return
        yield self.create_text_message(response.text)
