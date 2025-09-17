import time
from typing import Optional
from dify_plugin.entities.model import (
    AIModelEntity,
    EmbeddingInputType,
    FetchFrom,
    I18nObject,
    ModelPropertyKey,
    ModelType,
    PriceType,
)
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    TextEmbeddingResult,
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
from dify_plugin import TextEmbeddingModel
from xinference_client.client.restful.restful_client import (
    Client,
    RESTfulEmbeddingModelHandle,
)
from models.xinference_helper import XinferenceHelper, validate_model_uid


class XinferenceTextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for Xinference text embedding model.
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

        credentials should be like:
        {
            'server_url': 'server url',
            'model_uid': 'model uid',
        }

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :param user: unique user id
        :param input_type: input type
        :return: embeddings result
        """
        server_url = credentials["server_url"]
        model_uid = credentials["model_uid"]
        api_key = credentials.get("api_key")
        server_url = server_url.removesuffix("/")
        auth_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        try:
            handle = RESTfulEmbeddingModelHandle(model_uid, server_url, auth_headers)
            if "jina-embeddings-v4" in model_uid or "jina-embeddings-v4" in model:
                extra_body = {"task": "retrieval"}
                embeddings = handle.create_embedding(input=texts, **extra_body)
            else:
                embeddings = handle.create_embedding(input=texts)
        except RuntimeError as e:
            raise InvokeServerUnavailableError(str(e))
        '\n        for convenience, the response json is like:\n        class Embedding(TypedDict):\n            object: Literal["list"]\n            model: str\n            data: List[EmbeddingData]\n            usage: EmbeddingUsage\n        class EmbeddingUsage(TypedDict):\n            prompt_tokens: int\n            total_tokens: int\n        class EmbeddingData(TypedDict):\n            index: int\n            object: str\n            embedding: List[float]\n        '
        usage = embeddings["usage"]
        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=usage["total_tokens"]
        )
        result = TextEmbeddingResult(
            model=model,
            embeddings=[embedding["embedding"] for embedding in embeddings["data"]],
            usage=usage,
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
        :return: number of tokens for each text
        """
        return [self._get_num_tokens_by_gpt2(text) for text in texts]

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            if not validate_model_uid(credentials):
                raise CredentialsValidateFailedError(
                    "model_uid should not contain /, ?, or #"
                )
            server_url = credentials["server_url"]
            model_uid = credentials["model_uid"]
            api_key = credentials.get("api_key")
            extra_args = XinferenceHelper.get_xinference_extra_parameter(
                server_url=server_url, model_uid=model_uid, api_key=api_key
            )
            if extra_args.max_tokens:
                credentials["max_tokens"] = extra_args.max_tokens
            server_url = server_url.removesuffix("/")
            client = Client(base_url=server_url, api_key=api_key)
            try:
                handle = client.get_model(model_uid=model_uid)
            except RuntimeError as e:
                raise InvokeAuthorizationError(e)
            if not isinstance(handle, RESTfulEmbeddingModelHandle):
                raise InvokeBadRequestError(
                    "please check model type, the model you want to invoke is not a text embedding model"
                )
            self._invoke(model=model, credentials=credentials, texts=["ping"])
        except InvokeAuthorizationError as e:
            raise CredentialsValidateFailedError(
                f"Failed to validate credentials for model {model}: {e}"
            )
        except RuntimeError as e:
            raise CredentialsValidateFailedError(e)

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        return {
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [KeyError],
        }

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

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        used to define customizable model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.TEXT_EMBEDDING,
            model_properties={
                ModelPropertyKey.MAX_CHUNKS: 1,
                ModelPropertyKey.CONTEXT_SIZE: "max_tokens" in credentials
                and credentials["max_tokens"]
                or 512,
            },
            parameter_rules=[],
        )
        return entity
