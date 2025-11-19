import json
import requests
from collections.abc import Generator
from typing import Any, Dict, List

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GptImageTool(Tool):
    """
    GPT Image Generation Tool
    Uses opanai/gpt-image-1 model for fast image generation
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    
    def get_endpoint(self, model: str) -> str:
        """Get the appropriate endpoint based on model selection"""
        if model == "gpt-image-1-mini":
            return f"{self.BASE_URL}/models/opanai/gpt-image-1-mini/predictions"
        else:  # default to gpt-image-1
            return f"{self.BASE_URL}/models/opanai/gpt-image-1/predictions"
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for GPT Image generation
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise Exception("Prompt is required")
            
            model = tool_parameters.get("model", "gpt-image-1")
            resolution = tool_parameters.get("resolution", "1024x1024")
            num_images = int(tool_parameters.get("num_images", 1))
            quality = tool_parameters.get("quality", "high")
            moderation = tool_parameters.get("moderation", "low")
            background = tool_parameters.get("background", "auto")
            
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
            
            # Prepare request payload for GPT Image according to API documentation
            payload = {
                "input": {
                    "prompt": prompt,
                    "size": resolution,
                    "n": num_images,
                    "quality": quality,
                    "moderation": moderation,
                    "background": background
                }
            }
            
            yield self.create_text_message(f"Generating {num_images} image(s) with GPT Image using model: {model}...")
            
            # Make API request
            response = requests.post(
                self.get_endpoint(model),
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                error_msg = f"GPT Image API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
                except:
                    pass
                raise Exception(error_msg)
            
            data = response.json()
            
            # Extract image data from response (handle both URL and base64)
            images = []
            if "output" in data:
                output = data["output"]
                # Handle different response structures
                if isinstance(output, list):
                    # Standard format: [{"b64_json": "..."} or {"url": "..."}]
                    for item in output:
                        if "b64_json" in item:
                            images.append({"b64_json": item["b64_json"]})
                        elif "url" in item:
                            images.append({"url": item["url"]})
                elif isinstance(output, dict):
                    # Alternative format: {"b64_json": [{"bytesBase64": "..."}]}
                    if "b64_json" in output and isinstance(output["b64_json"], list):
                        for item in output["b64_json"]:
                            if "bytesBase64" in item:
                                images.append({"b64_json": item["bytesBase64"]})
                            elif "b64_json" in item:
                                images.append({"b64_json": item["b64_json"]})
            
            if not images:
                raise Exception("No images were generated")
            
            # Create image messages for direct display in Dify
            for img in images:
                if "url" in img:
                    yield self.create_image_message(img["url"])
                elif "b64_json" in img:
                    # For base64 images, create data URL
                    data_url = f"data:image/png;base64,{img['b64_json']}"
                    yield self.create_image_message(data_url)
            
            # Return results as JSON
            yield self.create_json_message({
                "success": True,
                "model": f"opanai/{model}",
                "prompt": prompt,
                "resolution": resolution,
                "num_images": len(images),
                "images": images,
                "quality": quality,
                "moderation": moderation,
                "background": background
            })
            
            # Also create text message with image info
            image_info = []
            for i, img in enumerate(images, 1):
                if "url" in img:
                    image_info.append(f"- Image {i}: {img['url']}")
                elif "b64_json" in img:
                    image_info.append(f"- Image {i}: [Base64 encoded image data]")
            
            yield self.create_text_message(f"GPT Image generated {len(images)} image(s):\n" + "\n".join(image_info))
                
        except Exception as e:
            raise Exception(f"GPT Image generation failed: {str(e)}")
