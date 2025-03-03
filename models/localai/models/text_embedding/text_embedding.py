import time
from json import JSONDecodeError, dumps
from typing import Optional
from dify_plugin import TextEmbeddingModel
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
from requests import post
from yarl import URL


class LocalAITextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for LocalAI text embedding model.
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
        if len(texts) != 1:
            raise InvokeBadRequestError("Only one text is supported")
        server_url = credentials["server_url"]
        model_name = model
        if not server_url:
            raise CredentialsValidateFailedError("server_url is required")
        if not model_name:
            raise CredentialsValidateFailedError("model_name is required")
        url = server_url
        headers = {"Authorization": "Bearer 123", "Content-Type": "application/json"}
        data = {"model": model_name, "input": texts[0]}
        try:
            response = post(
                str(URL(url) / "embeddings"),
                headers=headers,
                data=dumps(data),
                timeout=10,
            )
        except Exception as e:
            raise InvokeConnectionError(str(e))
        if response.status_code != 200:
            try:
                resp = response.json()
                code = resp["error"]["code"]
                msg = resp["error"]["message"]
                if code == 500:
                    raise InvokeServerUnavailableError(msg)
                if response.status_code == 401:
                    raise InvokeAuthorizationError(msg)
                elif response.status_code == 429:
                    raise InvokeRateLimitError(msg)
                elif response.status_code == 500:
                    raise InvokeServerUnavailableError(msg)
                else:
                    raise InvokeError(msg)
            except JSONDecodeError as e:
                raise InvokeServerUnavailableError(
                    f"Failed to convert response to json: {e} with text: {response.text}"
                )
        try:
            resp = response.json()
            embeddings = resp["data"]
            usage = resp["usage"]
        except Exception as e:
            raise InvokeServerUnavailableError(
                f"Failed to convert response to json: {e} with text: {response.text}"
            )
        usage = self._calc_response_usage(
            model=model, credentials=credentials, tokens=usage["total_tokens"]
        )
        result = TextEmbeddingResult(
            model=model,
            embeddings=[[float(data) for data in x["embedding"]] for x in embeddings],
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
        :return:
        """
        return [self._get_num_tokens_by_gpt2(text) for text in texts]

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        Get customizable model schema

        :param model: model name
        :param credentials: model credentials
        :return: model schema
        """
        return AIModelEntity(
            model=model,
            label=I18nObject(zh_Hans=model, en_US=model),
            model_type=ModelType.TEXT_EMBEDDING,
            features=[],
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_properties={
                ModelPropertyKey.CONTEXT_SIZE: int(
                    credentials.get("context_size", "512")
                ),
                ModelPropertyKey.MAX_CHUNKS: 1,
            },
            parameter_rules=[],
        )

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self._invoke(model=model, credentials=credentials, texts=["ping"])
        except InvokeAuthorizationError:
            raise CredentialsValidateFailedError("Invalid credentials")
        except InvokeConnectionError as e:
            raise CredentialsValidateFailedError(f"Invalid credentials: {e}")

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
