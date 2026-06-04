from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from .firecrawl_appx import FirecrawlApp, get_array_params, get_json_params


class ScrapeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        the api doc:
        https://docs.firecrawl.dev/api-reference/endpoint/scrape
        """
        app = FirecrawlApp(
            api_key=self.runtime.credentials.get("firecrawl_api_key"), base_url=self.runtime.credentials.get("base_url")
        )
        payload = {}
        formats = get_array_params(tool_parameters, "formats") or []
        payload["onlyMainContent"] = tool_parameters.get("onlyMainContent", True)
        payload["includeTags"] = get_array_params(tool_parameters, "includeTags")
        payload["excludeTags"] = get_array_params(tool_parameters, "excludeTags")
        payload["headers"] = get_json_params(tool_parameters, "headers")
        payload["waitFor"] = tool_parameters.get("waitFor", 0)
        payload["timeout"] = tool_parameters.get("timeout", 30000)
        # v2: structured/LLM extraction is expressed as a "json" format object inside
        # the formats array (the v1 top-level "extract" field was removed).
        json_format = {"type": "json"}
        json_format["schema"] = get_json_params(tool_parameters, "schema")
        # v2 removed the json format's "systemPrompt" field (only "prompt"/"schema" remain),
        # so fold any provided system prompt into the single "prompt" field.
        system_prompt = tool_parameters.get("systemPrompt")
        prompt = tool_parameters.get("prompt")
        if system_prompt:
            prompt = f"{system_prompt}\n\n{prompt}" if prompt else system_prompt
        json_format["prompt"] = prompt
        json_format = {k: v for (k, v) in json_format.items() if v not in (None, "")}
        if len(json_format) > 1:  # has more than just {"type": "json"}
            formats = [f for f in formats if f != "extract"]
            formats.append(json_format)
        payload["formats"] = formats or None
        payload = {k: v for (k, v) in payload.items() if v not in (None, "")}
        crawl_result = app.scrape_url(url=tool_parameters["url"], **payload)
        markdown_result = crawl_result.get("data", {}).get("markdown", "")
        yield self.create_text_message(markdown_result)
        yield self.create_json_message(crawl_result)
