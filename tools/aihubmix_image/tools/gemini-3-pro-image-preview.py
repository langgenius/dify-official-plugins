"""
Gemini 3 Pro Image Generation Tool

Supports:
- Text-to-Image: Generate images from text prompts
- Image-to-Image: Transform existing images with prompts
- Multi-image Input: Use multiple reference images for consistent output
"""

from collections.abc import Generator
from typing import Any, List, Optional
import base64
import io

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

try:
    from PIL import Image
    from google import genai
    from google.genai import types
except ImportError:
    raise ImportError("Required packages not found. Please install: pip install google-genai Pillow")


class Gemini3ProImagePreviewTool(Tool):
    """
    Gemini 3 Pro Image Generation Tool
    
    Uses Google's Gemini models through AIHubMix for advanced image generation.
    Supports text-to-image, image-to-image transformation, and multi-image reference.
    """
    
    BASE_URL = "https://aihubmix.com/gemini"
    
    # Generation modes
    MODE_TEXT_TO_IMAGE = "text_to_image"
    MODE_IMAGE_TO_IMAGE = "image_to_image"
    
    def create_image_info(self, base64_data: str, aspect_ratio: str, resolution: str, image_format: str = "png") -> dict:
        mime_type = {
            "png": "image/png",
            "jpeg": "image/jpeg",
            "webp": "image/webp"
        }.get(image_format, "image/png")
        
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "format": image_format
        }
    
    def _process_image_input(self, image_input: Any) -> Optional[Image.Image]:
        """
        Process image input from various sources and return PIL Image object
        
        Args:
            image_input: Can be URL string, data URL, base64 string, or Dify file object
            
        Returns:
            PIL Image object or None if invalid
        """
        if not image_input:
            return None
        
        try:
            image_str = str(image_input).strip()
            
            # Check if it's a Dify file transfer variable or file object
            if isinstance(image_input, dict):
                # Dify file variable format
                if "type" in image_input and image_input["type"] == "image":
                    # Extract image data from file object
                    if "transfer_method" in image_input:
                        if image_input["transfer_method"] == "remote_url":
                            url = image_input.get("url", "")
                            if url:
                                return self._load_image_from_url(url)
                        elif image_input["transfer_method"] == "local_file":
                            # Handle base64 data
                            if "base64_data" in image_input:
                                return self._load_image_from_base64(image_input["base64_data"])
                    elif "url" in image_input:
                        return self._load_image_from_url(image_input["url"])
                    elif "base64_data" in image_input:
                        return self._load_image_from_base64(image_input["base64_data"])
            
            # HTTP/HTTPS URL
            if image_str.startswith('http://') or image_str.startswith('https://'):
                return self._load_image_from_url(image_str)
            
            # Data URL format
            if image_str.startswith('data:image/'):
                return self._load_image_from_data_url(image_str)
            
            # Base64 encoded image (with or without prefix)
            if image_str.startswith('iVBORw0KGgo') or '/' in image_str or '=' in image_str:
                return self._load_image_from_base64(image_str)
            
            return None
            
        except Exception as e:
            raise InvokeError(f"Failed to process image input: {str(e)}")
    
    def _load_image_from_url(self, url: str) -> Image.Image:
        """Load image from HTTP/HTTPS URL"""
        import requests
        response = requests.get(url, timeout=30)
        if response.status_code != 200:
            raise InvokeError(f"Failed to download image from URL: {url}")
        return Image.open(io.BytesIO(response.content))
    
    def _load_image_from_base64(self, base64_data: str) -> Image.Image:
        """Load image from base64 string"""
        image_bytes = base64.b64decode(base64_data)
        return Image.open(io.BytesIO(image_bytes))
    
    def _load_image_from_data_url(self, data_url: str) -> Image.Image:
        """Load image from data URL"""
        if ',' in data_url:
            base64_data = data_url.split(',')[1]
            return self._load_image_from_base64(base64_data)
        raise InvokeError("Invalid data URL format")
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            # Generation mode
            generation_mode = tool_parameters.get("generation_mode", self.MODE_TEXT_TO_IMAGE)
            
            # Image inputs for image-to-image or multi-image reference
            reference_images_str = tool_parameters.get("reference_images", "").strip()
            single_image_str = tool_parameters.get("image", "").strip()
            
            # Generation parameters
            aspect_ratio = tool_parameters.get("aspect_ratio", "1:1")
            resolution = tool_parameters.get("resolution", "4K")
            image_format = tool_parameters.get("image_format", "png")
            
            # Validate parameters
            valid_ratios = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"]
            if aspect_ratio not in valid_ratios:
                raise InvokeError(f"Invalid aspect ratio. Must be one of: {', '.join(valid_ratios)}")
            
            valid_resolutions = ["1K", "2K", "4K"]
            if resolution not in valid_resolutions:
                raise InvokeError(f"Invalid resolution. Must be one of: {', '.join(valid_resolutions)}")
            
            valid_formats = ["png", "jpeg", "webp"]
            if image_format not in valid_formats:
                raise InvokeError(f"Invalid image format. Must be one of: {', '.join(valid_formats)}")
            
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            # Initialize Google GenAI client
            client = genai.Client(
                api_key=api_key,
                http_options={"base_url": self.BASE_URL}
            )
            
            # Prepare contents list
            contents = [prompt]
            
            # Load reference images based on mode
            reference_images: List[Image.Image] = []
            
            if generation_mode == self.MODE_IMAGE_TO_IMAGE:
                # Single image for transformation
                if single_image_str:
                    image = self._process_image_input(single_image_str)
                    if image:
                        reference_images.append(image)
                    else:
                        raise InvokeError("Failed to process reference image")
                elif reference_images_str:
                    # Support comma-separated URLs for multi-image
                    image_urls = [url.strip() for url in reference_images_str.split(',')]
                    for url in image_urls:
                        image = self._process_image_input(url)
                        if image:
                            reference_images.append(image)
                else:
                    raise InvokeError("Reference image is required for Image-to-Image mode")
                
                yield self.create_text_message(f"Processing {len(reference_images)} reference image(s) for image transformation...")
            
            elif reference_images_str:
                # Multi-image reference for text-to-image
                image_urls = [url.strip() for url in reference_images_str.split(',')]
                for url in image_urls:
                    image = self._process_image_input(url)
                    if image:
                        reference_images.append(image)
                
                if reference_images:
                    yield self.create_text_message(f"Processing {len(reference_images)} reference image(s) for multi-image generation...")
            
            # Add images to contents
            for img in reference_images:
                contents.append(img)
            
            # Check if Google Search is enabled
            use_google_search = tool_parameters.get("use_google_search", False)
            
            # Configure generation
            config = types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
                image_config=types.ImageConfig(
                    aspect_ratio=aspect_ratio,
                    image_size=resolution,
                ),
            )
            
            # Add Google Search tool if enabled
            if use_google_search:
                config.tools = [{"google_search": {}}]
                yield self.create_text_message("Google Search enabled - fetching real-time information...")
            
            model = tool_parameters.get("model", "gemini-3-pro-image-preview")
            
            yield self.create_text_message(f"Generating image with {model} (mode: {generation_mode}, {aspect_ratio}, {resolution})...")
            
            # Make API request
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            
            if not response:
                raise InvokeError("No valid response received from Gemini")
            
            # Process response
            images = []
            text_content = ""
            
            for part in response.parts:
                if part.text is not None:
                    text_content += part.text
                elif part.inline_data is not None:
                    try:
                        image = part.as_image()
                        if image:
                            # Convert to base64
                            img_byte_arr = io.BytesIO()
                            img_format = image.format if image.format else "PNG"
                            image.save(img_byte_arr, format=img_format)
                            img_byte_arr = img_byte_arr.getvalue()
                            base64_data = base64.b64encode(img_byte_arr).decode()
                            
                            image_info = self.create_image_info(base64_data, aspect_ratio, resolution, image_format)
                            images.append(image_info)
                    except Exception as e:
                        continue
            
            if not images:
                raise InvokeError("No images were generated in the response")
            
            # Return image files as blobs
            for idx, image_info in enumerate(images):
                base64_data = image_info["url"].split(",")[1]
                image_bytes = base64.b64decode(base64_data)
                
                file_extension = image_format if image_format != "jpeg" else "jpg"
                filename = f"gemini_image_{idx + 1}.{file_extension}"
                
                mime_type = {
                    "png": "image/png",
                    "jpeg": "image/jpeg",
                    "webp": "image/webp"
                }.get(image_format, "image/png")
                
                yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
            
            # Return metadata as JSON
            yield self.create_json_message({
                "success": True,
                "model": model,
                "prompt": prompt,
                "generation_mode": generation_mode,
                "num_reference_images": len(reference_images),
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "image_format": image_format,
                "num_images": len(images),
                "text_content": text_content
            })
            
            # Summary message - output text content if available, otherwise brief success message
            if text_content:
                yield self.create_text_message(text_content[:500])
                
        except Exception as e:
            raise InvokeError(f"Gemini image generation failed: {str(e)}")
