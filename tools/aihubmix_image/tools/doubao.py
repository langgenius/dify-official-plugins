import json
import requests
from collections.abc import Generator
from typing import Any, Dict, List

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class DoubaoTool(Tool):
    """
    Doubao Seedream Image Generation Tool
    Uses doubao-seedream-4-0-250828 model for high-quality Chinese image generation
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    PREDICTIONS_ENDPOINT = f"{BASE_URL}/models/doubao/doubao-seedream-4-0-250828/predictions"
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for Doubao Seedream image generation
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            size = tool_parameters.get("size", "2K")
            sequential_image_generation = tool_parameters.get("sequential_image_generation", "disabled")
            stream = tool_parameters.get("stream", False)
            response_format = tool_parameters.get("response_format", "url")
            watermark = tool_parameters.get("watermark", True)
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Prepare request payload for Doubao Seedream according to API documentation
            payload = {
                "input": {
                    "prompt": prompt,
                    "size": size,
                    "sequential_image_generation": sequential_image_generation,
                    "stream": stream,
                    "response_format": response_format,
                    "watermark": watermark
                }
            }
            
            yield self.create_text_message(f"Generating image with Doubao Seedream ({size} size)...")
            
            # Make API request
            response = requests.post(
                self.PREDICTIONS_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                error_msg = f"Doubao Seedream API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
                except:
                    pass
                raise InvokeError(error_msg)
            
            data = response.json()
            
            # Extract image URLs from response
            images = []
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if "url" in item:
                        images.append({"url": item["url"]})
            
            if not images:
                raise InvokeError("No images were generated")
            
            # Create image messages for direct display in Dify
            for img in images:
                yield self.create_image_message(img["url"])
            
            # Return results as JSON
            yield self.create_json_message({
                "success": True,
                "model": "doubao/doubao-seedream-4-0-250828",
                "prompt": prompt,
                "num_images": len(images),
                "images": images,
                "size": size,
                "sequential_image_generation": sequential_image_generation,
                "stream": stream,
                "response_format": response_format,
                "watermark": watermark
            })
            
            # Also create text message with image URLs
            image_urls = "\n".join([f"- {img['url']}" for img in images])
            yield self.create_text_message(f"Doubao Seedream generated {len(images)} image(s):\n{image_urls}")
                
        except Exception as e:
            raise InvokeError(f"Doubao Seedream image generation failed: {str(e)}")
