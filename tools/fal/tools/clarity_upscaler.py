import os
from typing import Any, Generator, TypeVar
import fal_client
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from dify_plugin.file.file import File

T = TypeVar('T')

class ClarityUpscalerTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        image_file: File | None = tool_parameters.get("image_file")
        image_url: str | None = tool_parameters.get("image_url")
        
        if not image_file and not image_url:
            yield self.create_text_message("No image file or URL provided")
            return
        
        # Define default parameters
        defaults = {
            "prompt": "masterpiece, best quality, highres",
            "upscale_factor": 2,
            "negative_prompt": "(worst quality, low quality, normal quality:2)",
            "creativity": 0.35,
            "resemblance": 0.6,
            "guidance_scale": 4,
            "num_inference_steps": 18,
            "enable_safety_checker": False
        }
        
        # Helper function to get parameter with default
        def get_param(key: str, default_value: T) -> T:
            value = tool_parameters.get(key)
            if value is None or value == "":
                return default_value
            return value
            
        # Apply defaults and handle special cases
        processed_params = {k: get_param(k, v) for k, v in defaults.items()}
        
        # Special handling for parameters with constraints
        processed_params["upscale_factor"] = max(1, processed_params["upscale_factor"])
        
        # Handle seed separately (can be None)
        seed = tool_parameters.get("seed")
        if seed == "":
            seed = None

        api_key = self.runtime.credentials["fal_api_key"]
        os.environ["FAL_KEY"] = api_key
        
        # If image file is provided, upload it first
        if image_file:
            image_binary = image_file.blob
            mime_type = image_file.mime_type
            try:
                image_url = fal_client.upload(image_binary, mime_type or "image/jpeg")
            except Exception as e:
                yield self.create_text_message(f"Error uploading image file: {str(e)}")
                return
        
        # Build arguments for the API call
        arguments = {
            "image_url": image_url,
            **processed_params
        }
        
        # Add seed if provided
        if seed is not None:
            arguments["seed"] = seed
        
        try:
            result = fal_client.subscribe("fal-ai/clarity-upscaler", arguments=arguments, with_logs=False)
            json_message = self.create_json_message(result)
            
            # Create a more user-friendly message with the result image
            if "image" in result and "url" in result["image"]:
                # Create an image message directly with the URL
                image_url = result["image"]["url"]
                image_message = self.create_image_message(image_url=image_url)
                yield from [json_message, image_message]
            else:
                text = "Image upscaled successfully, but no URL was returned."
                text_message = self.create_text_message(text)
                yield from [json_message, text_message]
        except Exception as e:
            yield self.create_text_message(f"Error upscaling image: {str(e)}")
