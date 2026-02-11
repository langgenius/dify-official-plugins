import json
import requests
import base64
from collections.abc import Generator
from typing import Any, Dict, List, Union

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class ErnieIragEditTool(Tool):
    """
    ERNIE iRAG Edit Tool
    Uses qianfan/ernie-irag-edit model for image-to-image editing
    
    Supports multiple input formats:
    - HTTP/HTTPS URLs
    - Data URLs (base64 encoded)
    - Dify file transfer variables
    - Base64 encoded strings
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    PREDICTIONS_ENDPOINT = f"{BASE_URL}/models/qianfan/ernie-irag-edit/predictions"
    
    def create_image_info(self, base64_data: str, guidance: float) -> dict:
        mime_type = "image/png"
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "guidance": guidance
        }
    
    def _process_image_input(self, image_input: Any) -> str:
        """
        Process image input from various sources and return a valid URL for API
        
        Args:
            image_input: Can be URL string, data URL, base64 string, or Dify file object
            
        Returns:
            Valid image URL for the API
        """
        if not image_input:
            raise InvokeError("Input image is required")
        
        image_str = str(image_input).strip()
        
        # Check if it's a Dify file transfer variable or file object
        if isinstance(image_input, dict):
            # Dify file variable format
            if "type" in image_input and image_input["type"] == "image":
                # Extract URL from file object
                if "transfer_method" in image_input:
                    if image_input["transfer_method"] == "remote_url":
                        return image_input.get("url", "")
                    elif image_input["transfer_method"] == "local_file":
                        # For local files, we need to use base64
                        if "base64_data" in image_input:
                            return f"data:image/png;base64,{image_input['base64_data']}"
                elif "url" in image_input:
                    return image_input["url"]
                elif "base64_data" in image_input:
                    return f"data:image/png;base64,{image_input['base64_data']}"
            # Fallback for other dict formats
            image_str = str(image_input)
        
        # Check if text contains URL (for workflow connections where user connected text output)
        # This handles cases where user connected 'text' output instead of 'files' output
        import re
        url_pattern = r'https?://[^\s\)]+'
        urls = re.findall(url_pattern, image_str)
        if urls:
            # Return first URL found in text
            return urls[0]
        
        # Already a valid URL format
        if image_str.startswith('http://') or image_str.startswith('https://'):
            return image_str
        
        # Data URL format
        if image_str.startswith('data:image/'):
            return image_str
        
        # Base64 encoded image (with or without prefix)
        if image_str.startswith('iVBORw0KGgo') or '/' in image_str or '=' in image_str:
            # Likely base64 encoded
            try:
                # Try to decode to verify it's valid base64
                base64.b64decode(image_str)
                return f"data:image/png;base64,{image_str}"
            except:
                pass
        
        # If none of the above, try as file path or unknown format
        raise InvokeError(
            f"Invalid image input format. Supported formats:\n"
            f"- HTTP/HTTPS URLs (https://example.com/image.png)\n"
            f"- Data URLs (data:image/png;base64,...)\n"
            f"- Base64 encoded image data\n"
            f"- Dify file transfer variables\n"
            f"Received: {image_str[:100]}..."
        )
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for ERNIE iRAG Edit
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Edit prompt is required")
            
            # Process image input from various sources
            image_input = tool_parameters.get("image", "")
            image_url = self._process_image_input(image_input)
            
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
            
            # Extract image data from response
            images = []
            if "output" in data and isinstance(data["output"], list):
                for item in data["output"]:
                    if "b64_json" in item:
                        images.append({"b64_json": item["b64_json"]})
                    elif "url" in item:
                        images.append({"url": item["url"]})
            
            if not images:
                raise InvokeError("No edited images were generated")
            
            # Process images - return as blobs for base64 data, or display URLs
            for idx, img in enumerate(images):
                if "b64_json" in img:
                    # Decode base64 and return as blob
                    base64_data = img["b64_json"]
                    image_bytes = base64.b64decode(base64_data)
                    filename = f"ernie_irag_edit_image_{idx + 1}.png"
                    mime_type = "image/png"
                    yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
                elif "url" in img:
                    # For URL responses, create image message
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
            image_urls = "\n".join([img['url'] for img in images])
            yield self.create_text_message(image_urls)
                
        except Exception as e:
            raise InvokeError(f"ERNIE iRAG Edit failed: {str(e)}")
