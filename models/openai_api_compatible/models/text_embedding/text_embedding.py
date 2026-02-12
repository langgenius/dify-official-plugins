from typing import Mapping, Optional, Union
import ipaddress
import json
import re
import logging
from urllib.parse import urlparse

import requests
import tiktoken

from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    I18nObject,
    ModelFeature,
)
from dify_plugin.entities.model.text_embedding import (
    TextEmbeddingResult,
    EmbeddingUsage,
)
from dify_plugin.errors.model import InvokeError, InvokeServerUnavailableError
from dify_plugin.interfaces.model.openai_compatible.text_embedding import (
    OAICompatEmbeddingModel,
)


logger = logging.getLogger(__name__)


class OpenAITextEmbeddingModel(OAICompatEmbeddingModel):
    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
        credentials = credentials or {}
        entity = super().get_customizable_model_schema(model, credentials)

        if "display_name" in credentials and credentials["display_name"] != "":
            entity.label = I18nObject(
                en_US=credentials["display_name"], zh_Hans=credentials["display_name"]
            )

        # Add vision feature if vision support is enabled
        vision_support = credentials.get("vision_support", "no_support")
        if vision_support == "support":
            if entity.features is None:
                entity.features = []
            if ModelFeature.VISION not in entity.features:
                entity.features.append(ModelFeature.VISION)

        return entity

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke text embedding model with multimodal support

        Supports both text-only and multimodal (text + image) inputs.
        When vision_support is enabled, texts can contain JSON with "text" and "image" fields.

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed (can be JSON strings for multimodal)
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        # Check if vision support is enabled
        vision_support = credentials.get("vision_support", "no_support")

        # Process inputs - convert to multimodal format if needed
        processed_inputs = []
        for text in texts:
            processed = self._process_input(text, vision_support == "support")
            processed_inputs.append(processed)

        # Apply prefix
        prefix = self._get_prefix(credentials, input_type)
        if prefix:
            processed_inputs = self._add_prefix_to_inputs(processed_inputs, prefix)

        # Get context size and max chunks from credentials or model properties
        context_size = self._get_context_size(model, credentials)
        max_chunks = self._get_max_chunks(model, credentials)

        # Truncate long texts (similar to Tongyi's approach)
        inputs = []
        for input_data in processed_inputs:
            if isinstance(input_data, list):
                # Multimodal - convert to text first
                text_parts = []
                for content in input_data:
                    if content.get("type") == "text":
                        text_parts.append(content.get("text", ""))
                    elif content.get("type") == "image_url":
                        text_parts.append(
                            f"[Image: {content.get('image_url', {}).get('url', '')}]"
                        )
                text = " ".join(text_parts) if text_parts else ""
            else:
                text = input_data if isinstance(input_data, str) else str(input_data)

            # Check token count and truncate if necessary
            num_tokens = self._get_num_tokens_by_gpt2(text)
            if num_tokens >= context_size:
                # Truncate to fit within context size
                cutoff = int(len(text) * (context_size / num_tokens))
                text = text[0:cutoff]

            inputs.append(text)

        # Call API in batches
        return self._embed_in_batches(model, credentials, inputs, user, input_type)

    def _embed_in_batches(
        self,
        model: str,
        credentials: dict,
        inputs: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Embed texts in batches, handling API limits.
        """
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        api_key = credentials.get("api_key", "")
        endpoint_model_name = credentials.get("endpoint_model_name", "") or model
        max_chunks = self._get_max_chunks(model, credentials)

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        batched_embeddings = []
        used_tokens = 0
        total_price = 0.0

        # Initialize with default values, will be updated from API response if available
        unit_price = 0.0
        price_unit = 0.0
        currency = "USD"

        try:
            # Process in batches
            for i in range(0, len(inputs), max_chunks):
                batch = inputs[i : i + max_chunks]

                payload = {
                    "model": endpoint_model_name,
                    "input": batch,
                }

                # Add encoding_format only if specified in credentials
                encoding_format = credentials.get("encoding_format")
                if encoding_format:
                    payload["encoding_format"] = encoding_format

                logger.info(
                    f"Embedding API Request to {endpoint_url}/embeddings (batch {i // max_chunks + 1}/{(len(inputs) + max_chunks - 1) // max_chunks})"
                )

                response = requests.post(
                    f"{endpoint_url}/embeddings",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )

                # Debug: log response on error
                if response.status_code != 200:
                    logger.error(
                        f"Embedding API Error {response.status_code}: {response.text[:1000]}"
                    )

                response.raise_for_status()

                result = response.json()

                # Extract embeddings
                for data in result["data"]:
                    batched_embeddings.append(data["embedding"])

                # Extract usage information from API response
                usage = result.get("usage") or {}
                tokens = usage.get("prompt_tokens") or usage.get("total_tokens") or 0
                used_tokens += tokens

                # Extract pricing information if provided by API
                total_price += usage.get("total_price", 0.0)

                # Use API provided values if available, otherwise keep defaults
                if "unit_price" in usage:
                    unit_price = usage.get("unit_price", 0.0)
                if "price_unit" in usage:
                    price_unit = usage.get("price_unit", 0.0)
                if "currency" in usage:
                    currency = usage.get("currency", "USD")

            return TextEmbeddingResult(
                embeddings=batched_embeddings,
                model=model,
                usage=EmbeddingUsage(
                    tokens=used_tokens,
                    total_tokens=used_tokens,
                    unit_price=unit_price,
                    price_unit=price_unit,
                    total_price=total_price,
                    currency=currency,
                    latency=0.0,  # Latency tracking would require timing each request
                ),
            )

        except requests.exceptions.RequestException as ex:
            raise InvokeServerUnavailableError(str(ex))
        except Exception as ex:
            raise InvokeError(str(ex))

    def _process_input(self, text: str, vision_enabled: bool) -> Union[str, list]:
        """
        Process input text, detecting and handling multimodal content.

        :param text: input text which may contain JSON with image data
        :param vision_enabled: whether vision support is enabled
        :return: processed content (str or list) for API
        """
        if not vision_enabled:
            return text

        # Try to parse as JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return self._format_multimodal_content(data)
        except json.JSONDecodeError:
            pass

        # Try to detect markdown image syntax: ![desc](url)
        if vision_enabled:
            content = self._extract_markdown_images(text)
            if content != text:
                return content

        # Try to detect plain image URLs
        if vision_enabled and self._is_image_url(text):
            return [{"type": "image_url", "image_url": {"url": text}}]

        return text

    def _format_multimodal_content(self, data: dict) -> Union[str, list]:
        """
        Format multimodal content dict to OpenAI API format.

        Expected format: {"text": "...", "image": "url_or_path"}
        """
        content = []

        # Add image if present
        if "image" in data and data["image"]:
            image_url = self._process_image_url(data["image"])
            if image_url:
                content.append({"type": "image_url", "image_url": {"url": image_url}})

        # Add text if present
        if "text" in data and data["text"]:
            content.append({"type": "text", "text": data["text"]})

        return content if content else data.get("text", "")

    def _validate_image_url(self, url: str) -> str:
        """
        Validate image URL to prevent SSRF attacks.
        Only allows http, https, and data:image URLs.
        Blocks localhost, private IPs, and internal networks.

        :param url: URL to validate
        :return: Validated URL or empty string if invalid
        """
        if not url:
            return ""

        # Allow data URIs (base64 encoded images)
        if url.startswith("data:image"):
            return url

        # Only allow http/https URLs
        if not (url.startswith("http://") or url.startswith("https://")):
            logger.warning(f"Blocked non-HTTP URL: {url[:50]}...")
            return ""

        # Parse URL to check for SSRF attempts
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname

            if not hostname:
                return ""

            # Block localhost
            if hostname in ("localhost", "127.0.0.1", "::1"):
                logger.warning(f"Blocked localhost URL: {url[:50]}...")
                return ""

            # Block private IP ranges
            try:
                ip = ipaddress.ip_address(hostname)
                # Check if it's private, loopback, link-local, or reserved
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                ):
                    logger.warning(f"Blocked private IP URL: {url[:50]}...")
                    return ""
            except ValueError:
                # Not an IP address, it's a hostname - allow it
                pass

            return url
        except Exception as e:
            logger.warning(f"URL validation failed: {e}")
            return ""

            # Block localhost
            if hostname in ("localhost", "127.0.0.1", "::1"):
                logger.warning(f"Blocked localhost URL: {url[:50]}...")
                return ""

            # Block private IP ranges
            import ipaddress

            try:
                ip = ipaddress.ip_address(hostname)
                # Check if it's private, loopback, link-local, or reserved
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_reserved
                ):
                    logger.warning(f"Blocked private IP URL: {url[:50]}...")
                    return ""
            except ValueError:
                # Not an IP address, it's a hostname - allow it
                pass

            return url
        except Exception as e:
            logger.warning(f"URL validation failed: {e}")
            return ""

    def _process_image_url(self, image: str) -> str:
        """
        Process image URL securely.

        Supports:
        - HTTP/HTTPS URLs (with SSRF protection)
        - Base64 data URIs (with or without prefix)

        Security: Blocks file:// URLs, localhost, and private networks.
        """
        if not image:
            return ""

        # Check if it's already a data URI
        if image.startswith("data:image"):
            return image

        # Validate and process HTTP/HTTPS URLs
        if image.startswith(("http://", "https://")):
            return self._validate_image_url(image)

        # Check if it's a base64 encoded image (without data URI prefix)
        if self._is_base64_image(image):
            image_format = self._detect_image_format_from_base64(image)
            return f"data:image/{image_format};base64,{image}"

        # Reject file:// URLs and local paths (security risk)
        logger.warning(f"Blocked local file path: {image[:50]}...")
        return ""

    def _is_base64_image(self, text: str) -> bool:
        """
        Check if text is a base64 encoded image (without data URI prefix).

        :param text: text to check
        :return: True if it's a base64 image string
        """
        import base64

        if not text or len(text) < 100:
            return False

        # Remove potential data URI prefix if present
        if "," in text:
            text = text.split(",", 1)[1]

        try:
            # Try to decode as base64
            decoded = base64.b64decode(text, validate=True)
            # Check if it looks like an image (at least 100 bytes)
            return len(decoded) > 100
        except Exception:
            return False

    def _detect_image_format_from_base64(self, base64_str: str) -> str:
        """
        Detect image format from base64 string by checking magic bytes.

        :param base64_str: base64 encoded image string
        :return: image format (jpeg, png, gif, webp, bmp)
        """
        import base64

        # Remove data URI prefix if present
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]

        try:
            data = base64.b64decode(base64_str, validate=True)

            # Check magic bytes
            if data.startswith(b"\xff\xd8\xff"):
                return "jpeg"
            elif data.startswith(b"\x89PNG\r\n\x1a\n"):
                return "png"
            elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
                return "gif"
            elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
                return "webp"
            elif data.startswith(b"BM"):
                return "bmp"
            else:
                # Default to jpeg if unknown
                return "jpeg"
        except Exception:
            return "jpeg"

    def _extract_markdown_images(self, text: str) -> Union[str, list]:
        """
        Extract markdown image syntax: ![description](url)

        :param text: text potentially containing markdown images
        :return: processed content
        """
        # Pattern to match markdown images
        pattern = r"!\[([^\]]*)\]\(([^\)]+)\)"

        matches = list(re.finditer(pattern, text))
        if not matches:
            return text

        content = []
        last_end = 0

        for match in matches:
            # Add text before image
            if match.start() > last_end:
                text_part = text[last_end : match.start()].strip()
                if text_part:
                    content.append({"type": "text", "text": text_part})

            # Add image
            image_url = match.group(2)
            content.append({"type": "image_url", "image_url": {"url": image_url}})

            last_end = match.end()

        # Add remaining text
        if last_end < len(text):
            text_part = text[last_end:].strip()
            if text_part:
                content.append({"type": "text", "text": text_part})

        return content

    def _is_image_url(self, text: str) -> bool:
        """Check if text is an image URL."""
        image_extensions = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg")
        return text.startswith(("http://", "https://")) and any(
            text.lower().endswith(ext) for ext in image_extensions
        )

    def _add_prefix_to_inputs(self, inputs: list, prefix: str) -> list:
        """Add prefix to text inputs."""
        result = []
        for item in inputs:
            if isinstance(item, str):
                result.append(f"{prefix} {item}")
            elif isinstance(item, list):
                # It's a multimodal content list
                for content in item:
                    if content.get("type") == "text":
                        content["text"] = f"{prefix} {content['text']}"
                result.append(item)
            else:
                result.append(item)
        return result

    def _get_prefix(self, credentials: dict, input_type: EmbeddingInputType) -> str:
        if input_type == EmbeddingInputType.DOCUMENT:
            return credentials.get("document_prefix", "")

        if input_type == EmbeddingInputType.QUERY:
            return credentials.get("query_prefix", "")

        return ""

    def _get_num_tokens_by_gpt2(self, text: str) -> int:
        """
        Get token count for text using GPT-2 tokenizer (tiktoken).

        :param text: text to count tokens for
        :return: number of tokens (approximate)
        """
        try:
            encoding = tiktoken.get_encoding("gpt2")
            return len(encoding.encode(text))
        except Exception:
            # Fallback to character count or a default if tiktoken fails
            return (
                len(text) // 4
            )  # Rough estimate if tiktoken is not available or fails

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        inputs: list,
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke embedding model with potentially multimodal inputs.
        This method delegates to _invoke for processing.
        """
        # Convert inputs back to texts format and use _invoke
        texts = []
        for input_data in inputs:
            if isinstance(input_data, list):
                # Multimodal - convert to text
                text_parts = []
                for content in input_data:
                    if content.get("type") == "text":
                        text_parts.append(content.get("text", ""))
                    elif content.get("type") == "image_url":
                        text_parts.append(
                            f"[Image: {content.get('image_url', {}).get('url', '')}]"
                        )
                texts.append(" ".join(text_parts) if text_parts else "")
            else:
                texts.append(
                    input_data if isinstance(input_data, str) else str(input_data)
                )

        return self._invoke(model, credentials, texts, user, input_type)
