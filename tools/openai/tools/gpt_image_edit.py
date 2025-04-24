import base64
import io
from collections.abc import Generator
from typing import Any, Dict
from openai import OpenAI
from yarl import URL
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from dify_plugin.file.file import File

class GPTImageEditTool(Tool):
    """
    Tool to edit images using OpenAI's gpt-image-1 model.
    It takes an input image and a prompt, and optionally a mask,
    to generate an edited version of the image.
    """
    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the image editing tool.
        """
        openai_organization = self.runtime.credentials.get(
            "openai_organization_id", None
        )
        if not openai_organization:
            openai_organization = None
        openai_base_url = self.runtime.credentials.get("openai_base_url", None)
        if not openai_base_url:
            openai_base_url = None
        else:
            openai_base_url = str(URL(openai_base_url) / "v1")

        client = OpenAI(
            api_key=self.runtime.credentials["openai_api_key"],
            base_url=openai_base_url,
            organization=openai_organization,
        )

        # --- Parameter Extraction and Validation ---
        prompt = tool_parameters.get("prompt")
        if not prompt or not isinstance(prompt, str):
            yield self.create_text_message("Error: Prompt is required.")
            return

        image = tool_parameters.get("image")
        if not image:
            yield self.create_text_message("Error: Input image file is required.")
            return
        
        edit_args: Dict[str, Any] = {
            "model": "gpt-image-1",  # Explicitly using gpt-image-1 as it supports multiple images
            "prompt": prompt,
        }

        # Handle single image or array of images
        if isinstance(image, list):
            image_files = []
            for img in image:
                if not isinstance(img, File):
                    yield self.create_text_message("Error: All input images must be valid files.")
                    return
                try:
                    img_bytes = img.blob
                    img_file = io.BytesIO(img_bytes)
                    img_file.name = getattr(img, 'filename', 'input_image.png')
                    image_files.append(img_file)
                except Exception as e:
                    yield self.create_text_message(f"Error processing input image: {e}")
                    # Clean up any opened files
                    for f in image_files:
                        if not f.closed:
                            f.close()
                    return
            edit_args["image"] = image_files
        else:
            if not isinstance(image, File):
                yield self.create_text_message("Error: Input image must be a valid file.")
                return
            try:
                image_bytes = image.blob
                image_file = io.BytesIO(image_bytes)
                image_file.name = getattr(image, 'filename', 'input_image.png')
                edit_args["image"] = image_file
            except Exception as e:
                yield self.create_text_message(f"Error processing input image: {e}")
                return

        # Mask (optional file input)
        mask = tool_parameters.get("mask")
        if mask and isinstance(mask, File):
            try:
                mask_bytes = mask.blob
                mask_file = io.BytesIO(mask_bytes)
                mask_file.name = getattr(mask, 'filename', 'mask_image.png')
                edit_args["mask"] = mask_file
            except Exception as e:
                 yield self.create_text_message(f"Warning: Could not process mask image: {e}. Proceeding without mask.")
                 if "mask" in edit_args: del edit_args["mask"]

        # Size (optional, defaults to auto)
        size = tool_parameters.get("size", "auto")
        if size not in {"1024x1024", "1536x1024", "1024x1536", "auto"}:
             yield self.create_text_message("Invalid size. Choose 1024x1024, 1536x1024, 1024x1536, or auto.")
             return
        if size != "auto":
            edit_args["size"] = size

        # Quality (optional, defaults to auto)
        quality = tool_parameters.get("quality", "auto")
        if quality not in {"low", "medium", "high", "auto"}:
             yield self.create_text_message("Invalid quality. Choose low, medium, high, or auto.")
             return
        if quality != "auto":
             edit_args["quality"] = quality

        # Number of images to generate (optional, defaults to 1)
        n = tool_parameters.get("n", 1)
        try:
            n = int(n)
            if not 1 <= n <= 10:
                yield self.create_text_message("Invalid n value. Must be between 1 and 10.")
                return
            edit_args["n"] = n
        except (TypeError, ValueError):
            yield self.create_text_message("Invalid n value. Must be a number between 1 and 10.")
            return

        # --- API Call ---
        try:
            response = client.images.edit(**edit_args)
        except Exception as e:
            # Attempt to close file handles if they exist
            if isinstance(edit_args.get("image"), list):
                for img_file in edit_args["image"]:
                    if not img_file.closed:
                        img_file.close()
            elif 'image_file' in locals() and not image_file.closed:
                image_file.close()
            if 'mask_file' in locals() and 'mask' in edit_args and not mask_file.closed:
                mask_file.close()
            yield self.create_text_message(f"Failed to edit image: {str(e)}")
            return
        finally:
            # Ensure all file handles are closed after API call
            if isinstance(edit_args.get("image"), list):
                for img_file in edit_args["image"]:
                    if not img_file.closed:
                        img_file.close()
            elif 'image_file' in locals() and not image_file.closed:
                image_file.close()
            if 'mask_file' in locals() and 'mask' in edit_args and not mask_file.closed:
                mask_file.close()

        # --- Process Response ---
        try:
            for image_data in response.data:
                if not image_data.b64_json:
                    continue
                
                # For edits, the output format isn't configurable via API for gpt-image-1,
                # it seems to follow input or defaults (likely PNG).
                # Let's assume PNG or decode if possible.
                try:
                    mime_type, blob_image = self._decode_image(image_data.b64_json)
                    
                    # Create metadata dictionary
                    metadata = {"mime_type": mime_type}
                    
                    # Add usage information if available
                    if hasattr(response, 'usage'):
                        usage_dict = {}
                        if hasattr(response.usage, 'total_tokens'):
                            usage_dict['total_tokens'] = response.usage.total_tokens
                        if hasattr(response.usage, 'input_tokens'):
                            usage_dict['input_tokens'] = response.usage.input_tokens
                        if hasattr(response.usage, 'output_tokens'):
                            usage_dict['output_tokens'] = response.usage.output_tokens
                        if hasattr(response.usage, 'input_tokens_details'):
                            usage_dict['input_tokens_details'] = {
                                'text_tokens': response.usage.input_tokens_details.text_tokens,
                                'image_tokens': response.usage.input_tokens_details.image_tokens
                            }
                        if usage_dict:
                            metadata['usage'] = usage_dict
                    
                    yield self.create_blob_message(
                        blob=blob_image,
                        meta=metadata
                    )
                except Exception as e:
                    yield self.create_text_message(f"Error processing response image: {str(e)}")
                    continue
        except Exception as e:
            yield self.create_text_message(f"Error processing response: {str(e)}")
            return

    @staticmethod
    def _decode_image(base64_image: str) -> tuple[str, bytes]:
        """
        Decode a base64 encoded image. Assumes 'image/png' if no prefix found.
        """
        if GPTImageEditTool._is_plain_base64(base64_image):
            return ("image/png", base64.b64decode(base64_image))
        else:
            return GPTImageEditTool._extract_mime_and_data(base64_image)

    @staticmethod
    def _is_plain_base64(encoded_str: str) -> bool:
        """Check if the string is plain base64."""
        return not encoded_str.startswith("data:image")

    @staticmethod
    def _extract_mime_and_data(encoded_str: str) -> tuple[str, bytes]:
        """Extract MIME type and data from prefixed base64 string."""
        try:
            mime_type = encoded_str.split(";")[0].split(":")[1]
            image_data_base64 = encoded_str.split(",")[1]
            decoded_data = base64.b64decode(image_data_base64)
            return (mime_type, decoded_data)
        except Exception:
            # Fallback for potentially malformed strings
            return ("image/png", base64.b64decode(encoded_str.split(',')[-1])) # Try decoding last part 