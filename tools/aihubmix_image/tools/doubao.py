import json
import requests
import base64
from collections.abc import Generator
from typing import Any, Dict, List, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class DoubaoTool(Tool):
    """
    Doubao Seedream Image Generation Tool
    Uses doubao-seedream-4-0-250828 and doubao-seedream-4-5 models for high-quality Chinese image generation.
    
    Supports three generation modes:
    - Text-to-Image: Generate images from text prompts
    - Image-to-Image: Transform existing images based on prompts
    - Sequential Generation: Create consistent series of images (storyboards, variations)
    """
    
    # API endpoints
    BASE_URL = "https://aihubmix.com/v1"
    
    # Model endpoints
    MODEL_SEEDREAM_4_0 = "doubao-seedream-4-0-250828"
    MODEL_SEEDREAM_4_5 = "doubao-seedream-4-5"
    
    def get_endpoint(self, model: str) -> str:
        """Get the appropriate endpoint based on model selection"""
        return f"{self.BASE_URL}/models/doubao/{model}/predictions"
    
    # Generation modes
    MODE_TEXT_TO_IMAGE = "text_to_image"
    MODE_IMAGE_TO_IMAGE = "image_to_image"
    MODE_SEQUENTIAL = "sequential"
    
    def create_image_info(self, base64_data: str, size: str) -> dict:
        mime_type = "image/png"
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "size": size
        }
    
    def _process_image_input(self, image_input: Any) -> str:
        """
        Process image input from various sources and return a valid URL/data URL for API
        
        Args:
            image_input: Can be URL string, data URL, base64 string, or Dify file object
            
        Returns:
            Valid image URL or data URL for the API
        """
        if not image_input:
            raise InvokeError("Reference image is required for Image-to-Image mode")
        
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
        
        # If none of the above, try as file path or return as-is
        return image_str
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for Doubao Seedream image generation
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            # Generation mode
            generation_mode = tool_parameters.get("generation_mode", self.MODE_TEXT_TO_IMAGE)
            
            # Image-to-image parameters
            reference_image_input = tool_parameters.get("reference_image", "")
            image_strength = float(tool_parameters.get("image_strength", 0.5))
            
            # Sequential generation options
            sequential_image_generation = tool_parameters.get("sequential_image_generation", "disabled")
            max_sequential_images = int(tool_parameters.get("max_sequential_images", 4))
            
            # Model selection
            model = tool_parameters.get("model", self.MODEL_SEEDREAM_4_0)
            
            # Common parameters
            size = tool_parameters.get("size", "2K")
            stream = tool_parameters.get("stream", False)
            response_format = tool_parameters.get("response_format", "url")
            watermark = tool_parameters.get("watermark", True)
            
            # Validate parameters based on mode
            if generation_mode == self.MODE_IMAGE_TO_IMAGE:
                if not reference_image_input:
                    raise InvokeError("Reference image is required for Image-to-Image mode")
            
            # Process reference image if in image-to-image mode
            reference_image = ""
            if generation_mode == self.MODE_IMAGE_TO_IMAGE:
                reference_image = self._process_image_input(reference_image_input)
            
            if sequential_image_generation == "enabled" and max_sequential_images < 1:
                raise InvokeError("Max sequential images must be at least 1")
            if sequential_image_generation == "enabled" and max_sequential_images > 8:
                raise InvokeError("Max sequential images cannot exceed 8")
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Prepare request payload based on generation mode
            input_payload = {
                "prompt": prompt,
                "size": size,
                "sequential_image_generation": sequential_image_generation,
                "stream": stream,
                "response_format": response_format,
                "watermark": watermark
            }
            
            # Add mode-specific parameters
            if generation_mode == self.MODE_IMAGE_TO_IMAGE:
                input_payload["image"] = reference_image
                input_payload["image_strength"] = image_strength
            
            if sequential_image_generation == "enabled":
                input_payload["sequential_image_generation_options"] = {
                    "max_images": max_sequential_images
                }
            
            payload = {"input": input_payload}
            
            # Generate status message based on mode
            mode_descriptions = {
                self.MODE_TEXT_TO_IMAGE: "文生图",
                self.MODE_IMAGE_TO_IMAGE: "图生图",
                self.MODE_SEQUENTIAL: "组图输出"
            }
            mode_name = mode_descriptions.get(generation_mode, generation_mode)
            
            if generation_mode == self.MODE_IMAGE_TO_IMAGE:
                # Truncate for display
                display_ref = reference_image[:50] if len(reference_image) > 50 else reference_image
                yield self.create_text_message(f"使用 Doubao Seedream 进行{mode_name}，参考图: {display_ref}...")
            elif generation_mode == self.MODE_SEQUENTIAL:
                yield self.create_text_message(f"使用 Doubao Seedream 进行{mode_name}，生成 {max_sequential_images} 张连贯图像...")
            else:
                yield self.create_text_message(f"使用 Doubao Seedream 进行{mode_name} ({size})...")
            
            # Make API request with dynamic endpoint
            endpoint = self.get_endpoint(model)
            response = requests.post(
                endpoint,
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
                    filename = f"doubao_image_{idx + 1}.png"
                    mime_type = "image/png"
                    yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
                elif "url" in img:
                    # For URL responses, create image message
                    yield self.create_image_message(img["url"])
            
            # Return results as JSON
            yield self.create_json_message({
                "success": True,
                "model": f"doubao/{model}",
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
            image_urls = "\n".join([img['url'] for img in images])
            yield self.create_text_message(image_urls)
                
        except Exception as e:
            raise InvokeError(f"Doubao Seedream image generation failed: {str(e)}")
