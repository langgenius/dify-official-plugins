import json
import requests
from collections.abc import Generator
from typing import Any, Dict, List

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class QwenImageEditTool(Tool):
    """
    Qwen Image Edit Tool
    Uses qianfan/qwen-image-edit model for image-to-image editing
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    PREDICTIONS_ENDPOINT = f"{BASE_URL}/models/qianfan/qwen-image-edit/predictions"
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for Qwen Image Edit
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Edit prompt is required")
            
            image_url = tool_parameters.get("image", "").strip()
            if not image_url:
                raise InvokeError("Input image URL is required")
            
            # Additional validation for image URL format
            if not (image_url.startswith('http://') or image_url.startswith('https://') or image_url.startswith('data:image/')):
                raise InvokeError(f"Invalid image URL format: {image_url}. URL must start with http://, https://, or data:image/")
            
            guidance = float(tool_parameters.get("guidance", 7.5))
            watermark = tool_parameters.get("watermark", False)
            
            # Validate parameters
            if guidance < 1.0 or guidance > 20.0:
                raise InvokeError("Guidance scale must be between 1.0 and 20.0")
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Prepare request payload for Qwen Image Edit according to API documentation
            payload = {
                "input": {
                    "prompt": prompt,
                    "image": image_url,
                    "guidance": guidance,
                    "watermark": watermark
                }
            }
            
            yield self.create_text_message(f"Editing image with Qwen Image Edit...")
            
            # Make API request
            response = requests.post(
                self.PREDICTIONS_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=300
            )
            
            if response.status_code != 200:
                error_msg = f"Qwen Image Edit API request failed with status {response.status_code}"
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
                raise InvokeError("No edited images were generated")
            
            # Create image messages for direct display in Dify
            for img in images:
                yield self.create_image_message(img["url"])
            
            # Return results as JSON
            yield self.create_json_message({
                "success": True,
                "model": "qianfan/qwen-image-edit",
                "prompt": prompt,
                "input_image": image_url,
                "num_images": len(images),
                "images": images,
                "guidance": guidance,
                "watermark": watermark
            })
            
            # Also create text message with image URLs
            image_urls = "\n".join([f"- {img['url']}" for img in images])
            yield self.create_text_message(f"Qwen Image Edit generated {len(images)} edited image(s):\n{image_urls}")
                
        except Exception as e:
            raise InvokeError(f"Qwen Image Edit failed: {str(e)}")
