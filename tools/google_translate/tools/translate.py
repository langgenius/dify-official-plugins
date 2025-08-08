from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GoogleTranslate(Tool):
    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
            return

        dest = tool_parameters.get("dest", "")

        # Handle custom destination language
        if dest == "custom":
            dest = tool_parameters.get("custom_dest", "")
            if not dest:
                yield self.create_text_message("Please provide a custom destination language code")
                return
        elif not dest:
            yield self.create_text_message("Invalid parameter destination language")
            return

        try:
            result = self._translate(content, dest)
            yield self.create_text_message(str(result))
        except Exception as e:
            yield self.create_text_message(f"Translation service error: {str(e)}")

    def _translate(self, content: str, dest: str) -> str:
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {"client": "gtx", "sl": "auto", "tl": dest, "dt": "t", "q": content}
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, params=params, headers=headers)
            response.raise_for_status()  # Raise an exception for bad status codes

            response_json = response.json()
            result = response_json[0]
            translated_text = "".join([item[0] for item in result if item[0]])
            return str(translated_text)
        except requests.exceptions.RequestException as e:
            return f"Network error: {str(e)}"
        except (KeyError, IndexError, TypeError) as e:
            return f"Error parsing translation response: {str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"
