import json
from typing import Any, Generator

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"


class PerplexityAITool(Tool):
    def _parse_response(self, response: dict) -> dict:
        """Parse the response from Perplexity AI API"""
        if "choices" in response and len(response["choices"]) > 0:
            message = response["choices"][0]["message"]
            return {
                "content": message.get("content", ""),
                "role": message.get("role", ""),
                "citations": response.get("citations", []),
            }
        else:
            return {"content": "Unable to get a valid response", "role": "assistant", "citations": []}

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        headers = {
            "Authorization": f"Bearer {self.runtime.credentials['perplexity_api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": tool_parameters.get("model", "sonar"),
            "messages": [
                {"role": "system", "content": "Be precise and concise."},
                {"role": "user", "content": tool_parameters["query"]},
            ],
            "max_tokens": tool_parameters.get("max_tokens", 4096),
            "temperature": tool_parameters.get("temperature", 0.7),
            "top_p": tool_parameters.get("top_p", 1),
            "top_k": tool_parameters.get("top_k", 5),
            "presence_penalty": tool_parameters.get("presence_penalty", 0),
            "frequency_penalty": tool_parameters.get("frequency_penalty", 1),
            "stream": False,
            "web_search_options": {
                "search_context_size": tool_parameters.get("search_context_size", "low"),
            },
        }
        if "search_recency_filter" in tool_parameters:
            payload["search_recency_filter"] = tool_parameters["search_recency_filter"]
        if "return_images" in tool_parameters:
            payload["return_images"] = tool_parameters["return_images"]
        if "return_related_questions" in tool_parameters:
            payload["return_related_questions"] = tool_parameters["return_related_questions"]
        if "search_domain_filter" in tool_parameters:
            payload["search_domain_filter"] = [] if tool_parameters["search_domain_filter"] == "" else [domain.strip() for domain in tool_parameters["search_domain_filter"].split(",")][:3]
        if "search_context_size" in tool_parameters:
            payload["web_search_options"]["search_context_size"] = tool_parameters["search_context_size"]
        response = requests.post(url=PERPLEXITY_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        valuable_res = self._parse_response(response.json())
        for resp in [
            self.create_json_message(valuable_res),
            self.create_text_message(json.dumps(valuable_res, ensure_ascii=False, indent=2)),
        ]:
            yield resp
