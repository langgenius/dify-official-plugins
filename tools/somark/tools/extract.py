import logging
import json
from typing import Any, Dict, Generator
import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)

class ExtractTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the Somark extraction tool.
        """
        # 1. Get parameters
        file = tool_parameters.get("file")
        if not file:
            yield self.create_text_message("Error: No file provided.")
            return

        # 2. Get configuration
        base_url = self.runtime.credentials.get("base_url")
        if not base_url:
            base_url = "https://somark.tech/api/v1"
            
        api_key = self.runtime.credentials.get("api_key")
        if not api_key:
             yield self.create_text_message("Error: API Key is required.")
             return

        # 3. Construct URL
        base_url = base_url.rstrip("/")
        url = f"{base_url}/extract/acc_sync"
        
        # 4. Prepare request
        try:
            files = {
                "file": (file.filename, file.blob, file.mime_type)
            }
            
            data = {
                "api_key": api_key,
                "lang": "auto",
                "output_formats": ["markdown"]
            }

            # 5. Send request
            response = requests.post(url, files=files, data=data, timeout=120)
            
            if response.status_code != 200:
                error_msg = f"Somark API Error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                yield self.create_text_message(error_msg)
                return

            # 6. Process response
            try:
                result = response.json()
            except json.JSONDecodeError:
                yield self.create_text_message(f"Error: Invalid JSON response from API. Content: {response.text}")
                return
            
            # Extract content
            text_content = ""
            if isinstance(result, dict):
                if "data" in result and isinstance(result["data"], dict) and "result" in result["data"]:
                     res_data = result["data"]["result"]
                     if isinstance(res_data, dict) and "outputs" in res_data and "markdown" in res_data["outputs"]:
                         text_content = res_data["outputs"]["markdown"]
                     else:
                         text_content = json.dumps(res_data, ensure_ascii=False)
                else:
                    text_content = json.dumps(result, ensure_ascii=False)
            else:
                text_content = str(result)

            yield self.create_text_message(text_content)

        except requests.exceptions.RequestException as e:
            logger.error(f"Somark Network Error: {str(e)}")
            yield self.create_text_message(f"Network error connecting to Somark API: {str(e)}")
        except Exception as e:
            logger.error(f"Somark Plugin Error: {str(e)}")
            yield self.create_text_message(f"Error invoking Somark API: {str(e)}")
