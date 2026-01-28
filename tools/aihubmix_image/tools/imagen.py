import json
import base64
import os
import time
import requests
from collections.abc import Generator
from typing import Any, Dict, List
from io import BytesIO

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError

try:
    from google import genai
    from google.genai import types
    from PIL import Image
except ImportError:
    raise InvokeError("Required packages not found. Please install: pip install google-genai Pillow")


class ImagenTool(Tool):
    """
    Google Imagen Image Generation Tool
    
    Advanced image generation using Google's Imagen models through multiple API approaches.
    Supports both Google GenAI SDK and direct REST API calls with fallback mechanisms
    for maximum compatibility and reliability.
    """
    
    # API configuration
    BASE_URL = "https://aihubmix.com/v1"
    
    def create_image_info(self, base64_data: str, aspect_ratio: str) -> dict:
        mime_type = "image/png"
        return {
            "url": f"data:{mime_type};base64,{base64_data}",
            "aspect_ratio": aspect_ratio
        }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main invoke method for Google Imagen image generation
        """
        try:
            # Extract and validate parameters
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            
            model = tool_parameters.get("model", "imagen-4.0-fast-generate-001")
            num_images = int(tool_parameters.get("num_images", 1))
            aspect_ratio = tool_parameters.get("aspect_ratio", "1:1")
            
            # Validate parameters
            if num_images < 1 or num_images > 4:
                raise InvokeError("Number of images must be between 1 and 4")
            
            # Validate aspect ratio
            valid_ratios = ["1:1", "9:16", "16:9", "3:4", "4:3"]
            if aspect_ratio not in valid_ratios:
                raise InvokeError(f"Aspect ratio must be one of: {', '.join(valid_ratios)}")
            
            # Get API key from credentials
            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")
            
            yield self.create_text_message(f"Generating {num_images} image(s) with Google Imagen ({model})...")
            
            # Try multiple API approaches
            success = False
            last_error = None
            
            # Method 1: Try Google GenAI SDK
            try:
                yield self.create_text_message("Trying Google GenAI SDK...")
                client = genai.Client(
                    api_key=api_key,
                    http_options={"base_url": "https://aihubmix.com/gemini"},
                )
                
                config = types.GenerateImagesConfig(
                    number_of_images=num_images,
                    aspect_ratio=aspect_ratio,
                )
                
                response = client.models.generate_images(
                    model=model,
                    prompt=prompt,
                    config=config
                )
                
                # Process generated images
                images = []
                if response and hasattr(response, 'generated_images') and response.generated_images:
                    for i, generated_image in enumerate(response.generated_images):
                        try:
                            # Convert image bytes to base64 for Dify display
                            image_bytes = generated_image.image.image_bytes
                            base64_image = base64.b64encode(image_bytes).decode('utf-8')
                            
                            # Store image info without base64 in JSON (for cleaner output)
                            images.append({
                                "index": i + 1,
                                "format": "png",
                                "size": len(image_bytes)
                            })
                            
                            # Return image as blob
                            filename = f"imagen_image_{i + 1}.png"
                            mime_type = "image/png"
                            yield self.create_blob_message(blob=image_bytes, meta={"mime_type": mime_type, "filename": filename})
                            
                        except Exception as e:
                            continue
                    
                    if images:
                        success = True
                        yield self.create_json_message({
                            "success": True,
                            "model": model,
                            "prompt": prompt,
                            "num_images": len(images),
                            "images": images,
                            "aspect_ratio": aspect_ratio,
                            "note": "Images are returned as blobs. Image data is not included in this JSON response for brevity."
                        })
                        return
                
            except Exception as e:
                last_error = f"Google GenAI SDK failed: {str(e)}"
                yield self.create_text_message(f"Method 1 failed: {last_error}")
            
            # Method 2: Try predictions endpoint
            try:
                yield self.create_text_message("Trying predictions endpoint...")
                endpoint = f"{self.BASE_URL}/models/google/{model}/predictions"
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "input": {
                        "prompt": prompt,
                        "numberOfImages": num_images,
                        "aspectRatio": aspect_ratio
                    }
                }
                
                response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    data = response.json()
                    images = []
                    
                    # Handle different response formats
                    if "output" in data:
                        output = data["output"]
                        if isinstance(output, list):
                            for i, item in enumerate(output):
                                if "b64_json" in item:
                                    base64_data = item["b64_json"]
                                    data_url = f"data:image/png;base64,{base64_data}"
                                    images.append({
                                        "index": i + 1,
                                        "format": "png",
                                        "size": len(base64_data)
                                    })
                                    yield self.create_image_message(data_url)
                                elif "url" in item:
                                    url = item["url"]
                                    images.append({
                                        "index": i + 1,
                                        "format": "png",
                                        "url": url
                                    })
                                    yield self.create_image_message(url)
                        elif isinstance(output, dict):
                            # Handle the format from feedback
                            if "files" in output and output["files"]:
                                for i, file_info in enumerate(output["files"]):
                                    if isinstance(file_info, dict) and "uri" in file_info:
                                        url = file_info["uri"]
                                        images.append({
                                            "index": i + 1,
                                            "format": "png",
                                            "url": url
                                        })
                                        yield self.create_image_message(url)
                            elif "images" in output and output["images"]:
                                for i, img_info in enumerate(output["images"]):
                                    if isinstance(img_info, dict):
                                        images.append({
                                            "index": i + 1,
                                            "format": img_info.get("format", "png"),
                                            "size": img_info.get("size", 0)
                                        })
                    
                    if images:
                        success = True
                        yield self.create_json_message({
                            "success": True,
                            "model": model,
                            "prompt": prompt,
                            "num_images": len(images),
                            "images": images,
                            "aspect_ratio": aspect_ratio,
                            "note": "Images are returned as blobs. Image data is not included in this JSON response for brevity."
                        })
                        return
                else:
                    last_error = f"Predictions endpoint failed: {response.status_code} {response.text}"
                    yield self.create_text_message(f"Method 2 failed: {last_error}")
                    
            except Exception as e:
                last_error = f"Predictions endpoint failed: {str(e)}"
                yield self.create_text_message(f"Method 2 failed: {last_error}")
            
            # Method 3: Try Gemini style endpoint
            try:
                yield self.create_text_message("Trying Gemini style endpoint...")
                endpoint = f"{self.BASE_URL}/imagen/generate"
                
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "num_images": num_images,
                    "aspect_ratio": aspect_ratio
                }
                
                response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
                
                if response.status_code == 200:
                    data = response.json()
                    images = []
                    
                    if "images" in data:
                        for i, img_data in enumerate(data["images"]):
                            if "url" in img_data:
                                url = img_data["url"]
                                images.append({
                                    "index": i + 1,
                                    "format": "png",
                                    "url": url
                                })
                                yield self.create_image_message(url)
                            elif "b64_json" in img_data:
                                base64_data = img_data["b64_json"]
                                data_url = f"data:image/png;base64,{base64_data}"
                                images.append({
                                    "index": i + 1,
                                    "format": "png",
                                    "size": len(base64_data)
                                })
                                yield self.create_image_message(data_url)
                    
                    if images:
                        success = True
                        yield self.create_json_message({
                            "success": True,
                            "model": model,
                            "prompt": prompt,
                            "num_images": len(images),
                            "images": images,
                            "aspect_ratio": aspect_ratio,
                            "note": "Images are returned as blobs. Image data is not included in this JSON response for brevity."
                        })
                        return
                else:
                    last_error = f"Gemini style failed: {response.status_code} {response.text}"
                    yield self.create_text_message(f"Method 3 failed: {last_error}")
                    
            except Exception as e:
                last_error = f"Gemini style failed: {str(e)}"
                yield self.create_text_message(f"Method 3 failed: {last_error}")
            
            # If all methods failed
            if not success:
                raise InvokeError(f"All API methods failed. Last error: {last_error}")
                
        except Exception as e:
            # Provide more detailed error information
            error_msg = f"Google Imagen image generation failed: {str(e)}"
            if "404" in str(e):
                error_msg += "\nPossible causes:\n1. Incorrect model name\n2. API endpoint not available\n3. Invalid API key or permissions"
            elif "401" in str(e) or "403" in str(e):
                error_msg += "\nPossible causes:\n1. Invalid API key\n2. Insufficient permissions\n3. API key expired"
            elif "429" in str(e):
                error_msg += "\nPossible causes:\n1. Rate limit exceeded\n2. Too many requests"
            
            raise InvokeError(error_msg)
