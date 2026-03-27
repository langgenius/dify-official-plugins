import base64
import binascii
import time
from decimal import Decimal
from typing import Optional
from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    PriceConfig,
    PriceType,
    ModelFeature,
)
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    TextEmbeddingResult,
    MultiModalContent,
    MultiModalEmbeddingResult,
    MultiModalContentType,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from volcenginesdkarkruntime.types.multimodal_embedding import (
    MultimodalEmbeddingContentPartTextParam,
    MultimodalEmbeddingContentPartImageParam,
)
from volcenginesdkarkruntime.types.multimodal_embedding.embedding_content_part_image_param import (
    ImageURL,
)

from models.client import ArkClientV3
from legacy.client import MaaSClient
from legacy.errors import (
    AuthErrors,
    BadRequestErrors,
    ConnectionErrors,
    MaasError,
    RateLimitErrors,
    ServerUnavailableErrors,
)
from models.text_embedding.models import get_model_config


class VolcengineMaaSTextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for VolcengineMaaS text embedding model.
    """

    def _invoke(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> TextEmbeddingResult:
        """
        Invoke text embedding model

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        if ArkClientV3.is_legacy(credentials):
            return self._generate_v2(model, credentials, texts, user)
        return self._generate_v3(model, credentials, texts, user)

    def _is_multimodal_model(self, model: str, credentials: dict):
        model_config = get_model_config(credentials=credentials)
        return ModelFeature.VISION in model_config.features

    def _generate_v2(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
    ) -> TextEmbeddingResult:
        client = MaaSClient.from_credential(credentials)
        resp = MaaSClient.wrap_exception(lambda: client.embeddings(texts))
        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=resp["usage"]["total_tokens"]
        )
        result = TextEmbeddingResult(
            model=model, embeddings=[v["embedding"] for v in resp["data"]], usage=usage
        )
        return result

    def _generate_v3(
        self,
        model: str,
        credentials: dict,
        texts: list[str],
        user: Optional[str] = None,
    ) -> TextEmbeddingResult:
        client = ArkClientV3.from_credentials(credentials)

        if self._is_multimodal_model(model, credentials):
            resp = client.multimodal_embeddings(input=self._transform_input_text(texts))
            usage = self._calc_response_usage(
                model=model,
                credentials=credentials,
                tokens=getattr(resp.usage, "total_tokens", 0),
            )
            result = TextEmbeddingResult(
                model=model, embeddings=[resp.data.embedding], usage=usage
            )
        else:
            resp = client.embeddings(texts)
            usage = self._calc_response_usage(
                model=model, credentials=credentials, tokens=resp.usage.total_tokens
            )
            result = TextEmbeddingResult(
                model=model, embeddings=[v.embedding for v in resp.data], usage=usage
            )
        return result

    def get_num_tokens(
        self, model: str, credentials: dict, texts: list[str]
    ) -> list[int]:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return:
        """
        tokens = []
        for text in texts:
            tokens.append(self._get_num_tokens_by_gpt2(text))
        return tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        if ArkClientV3.is_legacy(credentials):
            return self._validate_credentials_v2(model, credentials)
        return self._validate_credentials_v3(model, credentials)

    def _validate_credentials_v2(self, model: str, credentials: dict) -> None:
        try:
            self._invoke(model=model, credentials=credentials, texts=["ping"])
        except MaasError as e:
            raise CredentialsValidateFailedError(e.message)

    def _validate_credentials_v3(self, model: str, credentials: dict) -> None:
        try:
            if self._is_multimodal_model(model, credentials):
                self._invoke_multimodal(
                    model=model,
                    credentials=credentials,
                    documents=[
                        MultiModalContent(
                            content_type=MultiModalContentType.TEXT, content="ping"
                        )
                    ],
                )
            else:
                self._invoke(model=model, credentials=credentials, texts=["ping"])
        except Exception as e:
            raise CredentialsValidateFailedError(e)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {
            InvokeConnectionError: ConnectionErrors.values(),
            InvokeServerUnavailableError: ServerUnavailableErrors.values(),
            InvokeRateLimitError: RateLimitErrors.values(),
            InvokeAuthorizationError: AuthErrors.values(),
            InvokeBadRequestError: BadRequestErrors.values(),
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> AIModelEntity:
        """
        generate custom model entities from credentials
        """
        model_config = get_model_config(credentials)
        model_properties = {
            ModelPropertyKey.CONTEXT_SIZE: model_config.properties.context_size,
            ModelPropertyKey.MAX_CHUNKS: model_config.properties.max_chunks,
        }
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            model_type=ModelType.TEXT_EMBEDDING,
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties=model_properties,
            features=model_config.features,
            parameter_rules=[],
            pricing=PriceConfig(
                input=Decimal(credentials.get("input_price", 0)),
                unit=Decimal(credentials.get("unit", 0)),
                currency=credentials.get("currency", "USD"),
            ),
        )
        return entity

    def _calc_response_usage(
        self, model: str, credentials: dict, tokens: int
    ) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: input tokens
        :return: usage
        """
        input_price_info = self.get_price(
            model=model,
            credentials=credentials,
            price_type=PriceType.INPUT,
            tokens=tokens,
        )
        usage = EmbeddingUsage(
            tokens=tokens,
            total_tokens=tokens,
            unit_price=input_price_info.unit_price,
            price_unit=input_price_info.unit,
            total_price=input_price_info.total_amount,
            currency=input_price_info.currency,
            latency=time.perf_counter() - self.started_at,
        )
        return usage

    def _transform_input_multi_modal(self, documents: list[MultiModalContent]):
        inputs = []

        def detect_image_format(base64_str: str) -> str:
            if not base64_str:
                raise ValueError("Empty image content")

            data = base64_str.strip()
            if data.startswith("data:image/"):
                format_part = data[len("data:image/") :].split(";", 1)[0]
                if format_part:
                    normalized = format_part.lower()
                    alias_map = {
                        "jpg": "jpeg",
                        "tif": "tiff",
                        "dib": "bmp",
                        "j2c": "jp2",
                        "j2k": "jp2",
                        "jp2": "jp2",
                        "jpc": "jp2",
                        "jpf": "jp2",
                        "jpx": "jp2",
                    }
                    return alias_map.get(normalized, normalized)

            if data.startswith("data:") and "," in data:
                data = data.split(",", 1)[1]

            data = "".join(data.split())
            if not data:
                raise ValueError("Empty image content")

            if len(data) % 4:
                data += "=" * (4 - (len(data) % 4))

            try:
                header_bytes = base64.b64decode(data[:64], validate=False)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("Invalid base64 image content") from exc

            if header_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
                return "png"
            if header_bytes.startswith(b"\xff\xd8\xff"):
                return "jpeg"
            if header_bytes.startswith(b"GIF87a") or header_bytes.startswith(b"GIF89a"):
                return "gif"
            if header_bytes.startswith(b"RIFF") and header_bytes[8:12] == b"WEBP":
                return "webp"
            if header_bytes.startswith(b"BM"):
                return "bmp"
            if header_bytes.startswith(b"icns"):
                return "icns"
            if header_bytes.startswith(b"\x01\xda"):
                return "sgi"
            if header_bytes.startswith(b"II*\x00") or header_bytes.startswith(
                b"MM\x00*"
            ):
                return "tiff"
            if header_bytes.startswith(b"\x00\x00\x01\x00"):
                return "ico"
            if header_bytes.startswith(
                b"\x00\x00\x00\x0c\x6a\x50\x20\x20\x0d\x0a\x87\x0a"
            ):
                return "jp2"
            if (
                header_bytes.startswith(b"\xff\x4f")
                and header_bytes[2:4] == b"\xff\x51"
            ):
                return "jp2"
            if header_bytes[4:8] == b"ftyp":
                brand = header_bytes[8:12]
                if brand in {b"heic", b"heix", b"hevc", b"hevx"}:
                    return "heic"
                if brand in {b"mif1", b"msf1"}:
                    return "heif"
            raise ValueError("Unsupported image format")

        for document in documents:
            if document.content_type == MultiModalContentType.TEXT:
                inputs.append(
                    MultimodalEmbeddingContentPartTextParam(
                        text=document.content,
                        type="text",
                    )
                )
            elif document.content_type == MultiModalContentType.IMAGE:
                image_format = detect_image_format(document.content)
                inputs.append(
                    MultimodalEmbeddingContentPartImageParam(
                        image_url=ImageURL(
                            url="data:image/"
                            + image_format
                            + ";base64,"
                            + document.content
                        ),
                        type="image_url",
                    )
                )
            else:
                raise ValueError(f"Unsupported content type: {document.content_type}")
        return inputs

    def _transform_input_text(self, documents: list[str]):
        inputs = []
        for document in documents:
            inputs.append(
                MultimodalEmbeddingContentPartTextParam(
                    text=document,
                    type="text",
                )
            )
        return inputs

    def _invoke_multimodal(
        self,
        model: str,
        credentials: dict,
        documents: list[MultiModalContent],
        user: str | None = None,
        input_type: EmbeddingInputType = EmbeddingInputType.DOCUMENT,
    ) -> MultiModalEmbeddingResult:
        client = ArkClientV3.from_credentials(credentials)
        resp = client.multimodal_embeddings(
            input=self._transform_input_multi_modal(documents=documents)
        )
        usage = self._calc_response_usage(
            model=model,
            credentials=credentials,
            tokens=getattr(resp.usage, "total_tokens", 0),
        )
        result = MultiModalEmbeddingResult(
            model=model, embeddings=[resp.data.embedding], usage=usage
        )
        return result
