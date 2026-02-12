import base64
import ipaddress
import json
import logging
import re
from typing import Mapping, Optional, Union, Any
from urllib.parse import urlparse

import requests

from dify_plugin.entities.model import AIModelEntity, I18nObject, ModelFeature
from dify_plugin.entities.model.rerank import RerankDocument, RerankResult
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.interfaces.model.openai_compatible.rerank import OAICompatRerankModel
from dify_plugin.interfaces.model.rerank_model import MultiModalRerankResult
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeError,
    InvokeServerUnavailableError,
)


logger = logging.getLogger(__name__)


class OpenAIRerankModel(OAICompatRerankModel):
    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._invoke(
                model=model,
                credentials=credentials,
                query="What is the capital of the United States?",
                docs=[
                    "Carson City is the capital city of the American state of Nevada. At the 2010 United States "
                    "Census, Carson City had a population of 55,274.",
                    "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that "
                    "are a political division controlled by the United States. Its capital is Saipan.",
                    "Washington, D.C., formally the District of Columbia, is the capital city and federal district of "
                    "the United States. It is located on the east bank of the Potomac River.",
                ],
                score_threshold=0.8,
                top_n=3,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex)) from ex

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping | dict
    ) -> AIModelEntity:
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
        query: str,
        docs: list[str],
        score_threshold: Optional[float] = None,
        top_n: Optional[int] = None,
        user: Optional[str] = None,
    ) -> RerankResult:
        """
        Invoke rerank model (text-only mode).
        """
        if not docs:
            return RerankResult(model=model, docs=[])

        # Build API request
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        api_key = credentials.get("api_key", "")
        endpoint_model_name = credentials.get("endpoint_model_name", "") or model

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        # Simple string format for text-only mode
        # Use `top_n if top_n is not None else len(docs)` to correctly handle top_n=0
        payload = {
            "model": endpoint_model_name,
            "query": query,
            "documents": docs,
            "top_n": top_n if top_n is not None else len(docs),
        }

        try:
            logger.info(f"Rerank API Request (text mode) to {endpoint_url}/rerank")

            response = requests.post(
                f"{endpoint_url}/rerank",
                headers=headers,
                json=payload,
                timeout=60,
            )

            if response.status_code != 200:
                logger.error(
                    f"Rerank API Error {response.status_code}: {response.text[:1000]}"
                )

            response.raise_for_status()

            result = response.json()

            # Parse rerank results
            rerank_docs = []
            for item in result.get("results", []):
                index = item.get("index", 0)
                score = item.get("relevance_score", 0.0)

                if index < len(docs):
                    rerank_docs.append(
                        RerankDocument(
                            index=index,
                            score=score,
                            text=docs[index],
                        )
                    )

            # Sort by score (highest first)
            rerank_docs.sort(key=lambda x: x.score, reverse=True)

            # Apply top_n if specified
            if top_n:
                rerank_docs = rerank_docs[:top_n]

            # Apply score threshold
            if score_threshold is not None:
                rerank_docs = [
                    doc for doc in rerank_docs if doc.score >= score_threshold
                ]

            return RerankResult(
                model=model,
                docs=rerank_docs,
            )

        except requests.exceptions.RequestException as ex:
            raise InvokeServerUnavailableError(str(ex))
        except Exception as ex:
            raise InvokeError(str(ex))

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        query: MultiModalContent,
        docs: list[MultiModalContent],
        score_threshold: Optional[float] = None,
        top_n: Optional[int] = None,
        user: Optional[str] = None,
    ) -> MultiModalRerankResult:
        """
        Invoke rerank model with multimodal support.

        API Format (from vLLM/Qwen3-VL-Reranker docs):
        {
            "query": "query text string",  # Query is plain text string
            "documents": [  # Documents use ScoreMultiModalParam format
                {
                    "content": [
                        {"type": "text", "text": "..."},
                        {"type": "image_url", "image_url": {"url": "..."}}
                    ]
                }
            ]
        }

        Note: Query with image is NOT supported by this model architecture.
        Only documents can contain images.
        """
        if not docs:
            return MultiModalRerankResult(
                model=model,
                docs=[],
            )

        # Check if query is an image - this is not supported
        if query.content_type == MultiModalContentType.IMAGE:
            logger.warning(
                "Query with image is not supported by Qwen3-VL-Reranker. Converting to text."
            )
            # Convert image query to text description
            query_text = f"[Image: {query.content}]"
        else:
            query_text = (
                query.content if isinstance(query.content, str) else str(query.content)
            )

        # Build API request
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        api_key = credentials.get("api_key", "")
        endpoint_model_name = credentials.get("endpoint_model_name", "") or model

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}" if api_key else "",
        }

        # Convert documents to ScoreMultiModalParam format
        documents_params = []
        for i, doc in enumerate(docs):
            doc_param = self._to_score_multimodal_param(doc)
            documents_params.append(doc_param)
            logger.debug(
                f"Document {i}: {json.dumps(doc_param, ensure_ascii=False)[:200]}"
            )

        # Build payload according to vLLM/Qwen3 format
        # Use `top_n if top_n is not None else len(docs)` to correctly handle top_n=0
        payload = {
            "model": endpoint_model_name,
            "query": query_text,  # Plain text string
            "documents": documents_params,  # ScoreMultiModalParam format
            "top_n": top_n if top_n is not None else len(docs),
        }

        try:
            logger.info(
                f"Rerank API Request (multimodal mode) to {endpoint_url}/rerank"
            )
            logger.info(f"Query: {query_text[:100]}")
            logger.info(f"Documents count: {len(documents_params)}")
            logger.debug(f"Payload: {json.dumps(payload, ensure_ascii=False)[:1000]}")

            response = requests.post(
                f"{endpoint_url}/rerank",
                headers=headers,
                json=payload,
                timeout=60,
            )

            if response.status_code != 200:
                logger.error(
                    f"Rerank API Error {response.status_code}: {response.text[:1000]}"
                )

            response.raise_for_status()

            result = response.json()

            # Parse rerank results
            rerank_docs = []
            for item in result.get("results", []):
                index = item.get("index", 0)
                score = item.get("relevance_score", 0.0)

                if index < len(docs):
                    doc_content = (
                        docs[index].content
                        if isinstance(docs[index].content, str)
                        else str(docs[index].content)
                    )
                    rerank_docs.append(
                        RerankDocument(
                            index=index,
                            score=score,
                            text=doc_content,
                        )
                    )

            # Sort by score (highest first)
            rerank_docs.sort(key=lambda x: x.score, reverse=True)

            # Apply top_n if specified (check for None to allow top_n=0)
            if top_n is not None:
                rerank_docs = rerank_docs[:top_n]

            # Apply score threshold
            if score_threshold is not None:
                rerank_docs = [
                    doc for doc in rerank_docs if doc.score >= score_threshold
                ]

            return MultiModalRerankResult(
                model=model,
                docs=rerank_docs,
            )

        except requests.exceptions.RequestException as ex:
            raise InvokeServerUnavailableError(str(ex))
        except Exception as ex:
            raise InvokeError(str(ex))

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

    def _to_score_multimodal_param(self, content: MultiModalContent) -> dict:
        """
        Convert MultiModalContent to ScoreMultiModalParam format.

        ScoreMultiModalParam format (from vLLM docs):
        {
            "content": [
                {"type": "text", "text": "..."},
                {"type": "image_url", "image_url": {"url": "..."}}
            ]
        }

        Security: URLs are validated to prevent SSRF and LFI attacks.
        """
        content_list = []

        if content.content_type == MultiModalContentType.TEXT:
            text_content = (
                content.content
                if isinstance(content.content, str)
                else str(content.content)
            )
            content_list.append({"type": "text", "text": text_content})
        elif content.content_type == MultiModalContentType.IMAGE:
            # Process image URL securely
            image_url = content.content
            if isinstance(content.content, str):
                # Validate URL before using
                image_url = self._validate_image_url(content.content)
            elif isinstance(content.content, dict) and "url" in content.content:
                image_url = self._validate_image_url(content.content["url"])
            else:
                image_url = ""

            # Only add if URL is valid
            if image_url:
                content_list.append(
                    {"type": "image_url", "image_url": {"url": image_url}}
                )
        else:
            # Default to text
            text_content = str(content.content) if content.content else ""
            content_list.append({"type": "text", "text": text_content})

        return {"content": content_list}

    def _process_image_url(self, image: str) -> str:
        """
        Process image URL securely.

        Security: Blocks file:// URLs, localhost, and private networks.
        """
        return self._validate_image_url(image)

        # Check if it's a base64 encoded image
        if self._is_base64_image(image):
            image_format = self._detect_image_format_from_base64(image)
            return f"data:image/{image_format};base64,{image}"

        # Assume it's a URL or path
        return image

    def _is_base64_image(self, text: str) -> bool:
        """
        Check if text is a base64 encoded image.
        """
        if not text or len(text) < 100:
            return False

        if "," in text:
            text = text.split(",", 1)[1]

        try:
            decoded = base64.b64decode(text, validate=True)
            return len(decoded) > 100
        except Exception:
            return False

    def _detect_image_format_from_base64(self, base64_str: str) -> str:
        """
        Detect image format from base64 string.
        """
        if "," in base64_str:
            base64_str = base64_str.split(",", 1)[1]

        try:
            data = base64.b64decode(base64_str, validate=True)

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
                return "jpeg"
        except Exception:
            return "jpeg"
