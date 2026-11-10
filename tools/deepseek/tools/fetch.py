from collections.abc import Generator
from typing import Any
from urllib.parse import urlsplit

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools._client import DeepSeekClient


class DeepSeekFetchTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        url = tool_parameters.get("url")
        if not isinstance(url, str) or not url or len(url) > 8192:
            raise ValueError("URL must contain 1 to 8192 characters.")
        try:
            parsed = urlsplit(url)
            valid = (
                parsed.scheme in ("http", "https")
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and not any(character.isspace() for character in url)
            )
        except ValueError:
            valid = False
        if not valid:
            raise ValueError(
                "URL must be an HTTP/HTTPS URL without embedded credentials."
            )

        data = DeepSeekClient(self.runtime.credentials).fetch(url)
        yield self.create_json_message(data)
        yield self.create_text_message(data["content"])
