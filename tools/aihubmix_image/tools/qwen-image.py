import json
import requests
from collections.abc import Generator
from typing import Any, Dict, List

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class QwenImageTool(Tool):
    """
    Qwen Image Generation Tool
    Uses qianfan/qwen-image model optimized for Chinese prompts
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    PREDICTIONS_ENDPOINT = f"{BASE_URL}/models/qianfan/qwen-image/predictions"
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for Qwen Image generation
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise Exception("Prompt is required")
            
            resolution = tool_parameters.get("resolution", "1024x1024")
            num_images = int(tool_parameters.get("num_images", 1))
            refer_image = tool_parameters.get("refer_image", "")
            guidance = float(tool_parameters.get("guidance", 7.5))
            watermark = tool_parameters.get("watermark", False)
            
            # Validate parameters
            if num_images < 1 or num_images > 4:
                raise Exception("Number of images must be between 1 and 4")
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise Exception("API Key is required")
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Prepare request payload for Qwen Image according to API documentation
            payload = {
                "input": {
                    "prompt": prompt,
                    "refer_image": refer_image,
                    "n": num_images,
                    "size": resolution,
                    "guidance": guidance,
                    "watermark": watermark
                }
            }
            
            yield self.create_text_message(f"Generating {num_images} image(s) with Qwen Image...")
            
            # Make API request
            response = requests.post(
                self.PREDICTIONS_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                error_msg = f"Qwen Image API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
                except:
                    pass
                raise Exception(error_msg)
            
            data = response.json()
            
            # Extract image URLs from response
            images = []
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if "url" in item:
                        images.append({"url": item["url"]})
            
            if not images:
                raise Exception("No images were generated")
            
            # Create image messages for direct display in Dify
            for img in images:
                yield self.create_image_message(img["url"])
            
            # Return results as JSON
            yield self.create_json_message({
                "success": True,
                "model": "qianfan/qwen-image",
                "prompt": prompt,
                "resolution": resolution,
                "num_images": len(images),
                "images": images,
                "refer_image": refer_image,
                "guidance": guidance,
                "watermark": watermark
            })
            
            # Also create text message with image URLs
            image_urls = "\n".join([f"- {img['url']}" for img in images])
            yield self.create_text_message(f"Qwen Image generated {len(images)} image(s):\n{image_urls}")
                
        except Exception as e:
            raise Exception(f"Qwen Image generation failed: {str(e)}")
