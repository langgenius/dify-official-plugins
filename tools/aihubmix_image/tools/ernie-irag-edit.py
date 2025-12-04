import json
import requests
from collections.abc import Generator
from typing import Any, Dict, List

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class ErnieIragEditTool(Tool):
    """
    ERNIE iRAG Edit Tool
    Uses qianfan/ernie-irag-edit model for image-to-image editing
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    PREDICTIONS_ENDPOINT = f"{BASE_URL}/models/qianfan/ernie-irag-edit/predictions"
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for ERNIE iRAG Edit
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Edit prompt is required")
            
            image_url = tool_parameters.get("image", "").strip()
            if not image_url:
                raise InvokeError("Input image URL is required")
            
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
            
            # Prepare request payload for ERNIE iRAG Edit according to API documentation
            payload = {
                "input": {
                    "prompt": prompt,
                    "image": image_url,
                    "feature": "variation",  
                    "guidance": guidance,
                    "watermark": watermark
                }
            }
            
            yield self.create_text_message(f"Editing image with ERNIE iRAG Edit...")
            
            # Make API request
            response = requests.post(
                self.PREDICTIONS_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                error_msg = f"ERNIE iRAG Edit API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
                except requests.exceptions.JSONDecodeError:
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
                "model": "qianfan/ernie-irag-edit",
                "prompt": prompt,
                "input_image": image_url,
                "feature": "variation",
                "num_images": len(images),
                "images": images,
                "guidance": guidance,
                "watermark": watermark
            })
            
            # Also create text message with image URLs
            image_urls = "\n".join([f"- {img['url']}" for img in images])
            yield self.create_text_message(f"ERNIE iRAG Edit generated {len(images)} edited image(s):\n{image_urls}")
                
        except Exception as e:
            raise InvokeError(f"ERNIE iRAG Edit failed: {str(e)}")
