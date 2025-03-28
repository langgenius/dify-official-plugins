import json
import logging
import time
from typing import Optional
from dify_plugin import TextEmbeddingModel
from dify_plugin.entities.model import EmbeddingInputType, PriceType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, TextEmbeddingResult
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.lkeap.v20240522 import lkeap_client, models


logger = logging.getLogger(__name__)


class HunyuanTextEmbeddingModel(TextEmbeddingModel):
    """
    Model class for Hunyuan text embedding model.
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
        if model != "lke-text-embedding-v1":
            raise ValueError(f"Invalid model name '{model}'")

        # https://cloud.tencent.com/document/api/1772/115343
        client = self._setup_hunyuan_client(credentials)
        req = models.GetEmbeddingRequest()
        params = {"Model": model, "Inputs": texts}
        req.from_json_string(json.dumps(params))
        resp = client.GetEmbedding(req)
        token_usage = resp.Usage.TotalTokens
        result = TextEmbeddingResult(
            model=model,
            embeddings=[data.Embedding for data in resp.Data],
            usage=self._calc_response_usage(model=model, credentials=credentials, tokens=token_usage),
        )
        return result

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate credentials
        """
        try:
            client = self._setup_hunyuan_client(credentials)
            req = models.ChatCompletionsRequest()
            params = {
                "Model": model,
                "Messages": [{"Role": "user", "Content": "hello"}],
                "TopP": 1,
                "Temperature": 0,
                "Stream": False,
            }
            req.from_json_string(json.dumps(params))
            client.ChatCompletions(req)
        except Exception as e:
            raise CredentialsValidateFailedError(f"Credentials validation failed: {e}")

    def _setup_hunyuan_client(self, credentials):
        secret_id = credentials["secret_id"]
        secret_key = credentials["secret_key"]
        cred = credential.Credential(secret_id, secret_key)
        httpProfile = HttpProfile()
        httpProfile.endpoint = "lkeap.tencentcloudapi.com"
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        client = lkeap_client.LkeapClient(cred, "ap-guangzhou", clientProfile)
        return client

    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: input tokens
        :return: usage
        """
        input_price_info = self.get_price(
            model=model, credentials=credentials, price_type=PriceType.INPUT, tokens=tokens
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

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the error type thrown to the caller
        The value is the error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke error mapping
        """
        return {InvokeError: [TencentCloudSDKException]}

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
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
