import requests
import base64
from collections.abc import Generator
from typing import Any, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class FluxKontextTool(Tool):
    """
    Flux Kontext Image Generation Tool
    
    Advanced image generation tool supporting Flux models with
    synchronous processing capabilities for high-quality image generation.
    """
    
    # API endpoints configuration
    BASE_URL = "https://aihubmix.com/v1"
    SYNC_ENDPOINT = f"{BASE_URL}/images/generations"
    
    def create_image_info(self, base64_data: str, resolution: str) -> dict:
        mime_type = "image/png"
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "resolution": resolution
        }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for Flux image generation
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            model = tool_parameters.get("model", "FLUX.1-Kontext-pro")
            resolution = tool_parameters.get("resolution", "1024x1024")
            num_images = int(tool_parameters.get("num_images", 1))
            moderation_level = int(tool_parameters.get("moderation_level", 3))
            
            # Validate parameters
            if num_images < 1 or num_images > 4:
                raise InvokeError("Number of images must be between 1 and 4")
            
            if moderation_level < 0 or moderation_level > 6:
                raise InvokeError("Moderation level must be between 0 and 6")
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Use sync endpoint for all remaining models
            yield from self._generate_sync(headers, model, prompt, resolution, num_images, moderation_level)
                
        except Exception as e:
            raise InvokeError(f"Flux image generation failed: {str(e)}")
    
    def _generate_sync(self, headers: Dict[str, str], model: str, prompt: str, resolution: str, num_images: int, moderation_level: int) -> Generator[ToolInvokeMessage]:
        """
        Generate image using sync endpoint for FLUX.1-Kontext-pro and FLUX-1.1-pro
        """
        model_name = model.replace(".", "-")
        
        # Prepare request payload for sync Flux generation
        payload = {
            "prompt": prompt,
            "model": model,
            "n": num_images,
            "size": resolution,
            "safety_tolerance": moderation_level
        }
        
        yield self.create_text_message(f"Generating image with {model}...")
        
        # Make API request
        response = requests.post(
            self.SYNC_ENDPOINT,
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            error_msg = f"Flux sync generation request failed with status {response.status_code}"
            try:
                error_data = response.json()
                if "error" in error_data:
                    error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
            except:
                pass
            raise InvokeError(error_msg)
        
        data = response.json()
        
        # Extract image data from response
        images = []
        if "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
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
                filename = f"flux_kontext_image_{idx + 1}.png"
                mime_type = "image/png"
                yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
            elif "url" in img:
                # For URL responses, create image message
                yield self.create_image_message(img["url"])
        
        # Return results as JSON
        yield self.create_json_message({
            "success": True,
            "model": model,
            "prompt": prompt,
            "resolution": resolution,
            "num_images": len(images),
            "images": images,
            "moderation_level": moderation_level
        })
        
        # Also create text message with image URLs
        image_urls = "\n".join([img['url'] for img in images if 'url' in img])
        if image_urls:
            yield self.create_text_message(image_urls)
