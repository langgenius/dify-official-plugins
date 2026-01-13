import json
import requests
import base64
from collections.abc import Generator
from typing import Any, Dict, List

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class ErnieIragTool(Tool):
    """
    ERNIE iRAG Image Generation Tool
    Uses qianfan/irag-1.0 model for high-quality Chinese image generation
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    PREDICTIONS_ENDPOINT = f"{BASE_URL}/models/qianfan/irag-1.0/predictions"
    
    def create_image_info(self, base64_data: str, resolution: str) -> dict:
        mime_type = "image/png"
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "resolution": resolution
        }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for ERNIE iRAG image generation
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            refer_image = tool_parameters.get("refer_image", "")
            resolution = tool_parameters.get("resolution", "1024x1024")
            num_images = int(tool_parameters.get("num_images", 1))
            guidance = float(tool_parameters.get("guidance", 7.5))
            watermark = tool_parameters.get("watermark", False)
            
            # Validate parameters
            if num_images < 1 or num_images > 4:
                raise InvokeError("Number of images must be between 1 and 4")
            
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
            
            # Prepare request payload for ERNIE iRAG according to API documentation
            payload = {
                "input": {
                    "prompt": prompt,
                    "n": num_images,
                    "size": resolution,
                    "guidance": guidance,
                    "watermark": watermark
                }
            }
            
            # Only add refer_image if it's provided (non-empty)
            if refer_image:
                payload["input"]["refer_image"] = refer_image
            
            yield self.create_text_message(f"Generating {num_images} image(s) with ERNIE iRAG...")
            
            # Make API request
            response = requests.post(
                self.PREDICTIONS_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code != 200:
                error_msg = f"ERNIE iRAG API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
                except requests.exceptions.JSONDecodeError:
                    pass
                raise InvokeError(error_msg)
            
            data = response.json()
            
            # Extract image data from response
            images = []
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if "b64_json" in item:
                        images.append({"b64_json": item["b64_json"]})
                    elif "url" in item:
                        images.append({"url": item["url"]})
            
            if not images:
                raise InvokeError("No images were generated")
            
            # Process images - return as blobs for base64 data, or display URLs
            for idx, img in enumerate(images):
                if "b64_json" in img:
                    # Decode base64 and return as blob
                    base64_data = img["b64_json"]
                    image_bytes = base64.b64decode(base64_data)
                    filename = f"ernie_irag_image_{idx + 1}.png"
                    mime_type = "image/png"
                    yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
                elif "url" in img:
                    # For URL responses, create image message
                    yield self.create_image_message(img["url"])
            
            # Return results as JSON
            yield self.create_json_message({
                "success": True,
                "model": "qianfan/irag-1.0",
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
            yield self.create_text_message(f"ERNIE iRAG generated {len(images)} image(s):\n{image_urls}")
                
        except Exception as e:
            raise InvokeError(f"ERNIE iRAG image generation failed: {str(e)}")
