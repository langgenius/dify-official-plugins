import json
import logging
import time
import tiktoken
from typing import Optional

from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoRegionError,
    ServiceNotInRegionError,
    UnknownServiceError,
)

from dify_plugin.entities.model import EmbeddingInputType, PriceType, AIModelEntity, FetchFrom, ModelType
from dify_plugin.entities.model.text_embedding import EmbeddingUsage, TextEmbeddingResult
from dify_plugin.entities import I18nObject

from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin.interfaces.model.text_embedding_model import TextEmbeddingModel
from provider.get_bedrock_client import get_bedrock_client
from . import model_ids
from utils.inference_profile import (
    get_inference_profile_info,
    validate_inference_profile,
    extract_model_info_from_profile
)

logger = logging.getLogger(__name__)


class BedrockTextEmbeddingModel(TextEmbeddingModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.started_at = time.perf_counter()
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
        # Check if using inference profile
        model_id = model
        inference_profile_id = credentials.get("inference_profile_id")
        if inference_profile_id:
            # Get the full ARN from the profile ID
            profile_info = get_inference_profile_info(inference_profile_id, credentials)
            model_id = profile_info.get("inferenceProfileArn")
            if not model_id:
                raise InvokeError(f"Could not get ARN for inference profile {inference_profile_id}")
            logger.info(f"Using inference profile ARN: {model_id}")
            
            # Determine model prefix from underlying models
            underlying_models = profile_info.get("models", [])
            if underlying_models:
                first_model_arn = underlying_models[0].get("modelArn", "")
                if "foundation-model/" in first_model_arn:
                    underlying_model_id = first_model_arn.split("foundation-model/")[1]
                    model_prefix = underlying_model_id.split(".")[0]
                else:
                    raise InvokeError(f"Could not determine model type from inference profile")
            else:
                raise InvokeError(f"No underlying models found in inference profile")
        else:
            # Traditional model - use model directly
            model_prefix = model.split(".")[0]
            
        bedrock_runtime = get_bedrock_client("bedrock-runtime", credentials)

        embeddings = []
        token_usage = 0

        if model_prefix == "amazon":
            for text in texts:
                body = {
                    "inputText": text,
                }
                response_body = self._invoke_bedrock_embedding(model_id, bedrock_runtime, body)
                embeddings.extend([response_body.get("embedding")])
                token_usage += response_body.get("inputTextTokenCount")
            logger.warning(f"Total Tokens: {token_usage}")
            result = TextEmbeddingResult(
                model=model,
                embeddings=embeddings,
                usage=self._calc_response_usage(model=model, credentials=credentials, tokens=token_usage),
            )
            return result

        if model_prefix == "cohere":
            input_type = "search_document" if len(texts) > 1 else "search_query"
            for text in texts:
                body = {
                    "texts": [text],
                    "input_type": input_type,
                }
                response_body = self._invoke_bedrock_embedding(model_id, bedrock_runtime, body)
                embeddings.extend(response_body.get("embeddings"))
                token_usage += len(text)
            result = TextEmbeddingResult(
                model=model,
                embeddings=embeddings,
                usage=self._calc_response_usage(model=model, credentials=credentials, tokens=token_usage),
            )
            return result

        # others
        raise ValueError(f"Got unknown model prefix {model_prefix} when handling block response")

    def get_num_tokens(self, model: str, credentials: dict, texts: list[str]) -> list[int]:
        """
        Get number of tokens for given prompt messages

        :param model: model name
        :param credentials: model credentials
        :param texts: texts to embed
        :return:
        """
        if len(texts) == 0:
            return []

        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")

        total_num_tokens = []
        for text in texts:
            # calculate the number of tokens in the encoded text
            tokenized_text = enc.encode(text)
            total_num_tokens.append(len(tokenized_text))

        return total_num_tokens

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """

    @property
    def _invoke_error_mapping(self) -> dict[type[InvokeError], list[type[Exception]]]:
        """
        Map model invoke error to unified error
        The key is the ermd = genai.GenerativeModel(model) error type thrown to the caller
        The value is the md = genai.GenerativeModel(model) error type thrown by the model,
        which needs to be converted into a unified error type for the caller.

        :return: Invoke emd = genai.GenerativeModel(model) error mapping
        """
        return {
            InvokeConnectionError: [],
            InvokeServerUnavailableError: [],
            InvokeRateLimitError: [],
            InvokeAuthorizationError: [],
            InvokeBadRequestError: [],
        }

    def _create_payload(
        self,
        model_prefix: str,
        texts: list[str],
        model_parameters: dict,
        stop: Optional[list[str]] = None,
        stream: bool = True,
    ):
        """
        Create payload for bedrock api call depending on model provider
        """
        payload = {}

        if model_prefix == "amazon":
            payload["inputText"] = texts

    def _calc_response_usage(self, model: str, credentials: dict, tokens: int) -> EmbeddingUsage:
        """
        Calculate response usage

        :param model: model name
        :param credentials: model credentials
        :param tokens: input tokens
        :return: usage
        """
        # get input price info
        input_price_info = self.get_price(
            model=model, credentials=credentials, price_type=PriceType.INPUT, tokens=tokens
        )

        # transform usage
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

    def _map_client_to_invoke_error(self, error_code: str, error_msg: str) -> type[InvokeError]:
        """
        Map client error to invoke error

        :param error_code: error code
        :param error_msg: error message
        :return: invoke error
        """

        if error_code == "AccessDeniedException":
            return InvokeAuthorizationError(error_msg)
        elif error_code in {"ResourceNotFoundException", "ValidationException"}:
            return InvokeBadRequestError(error_msg)
        elif error_code in {"ThrottlingException", "ServiceQuotaExceededException"}:
            return InvokeRateLimitError(error_msg)
        elif error_code in {
            "ModelTimeoutException",
            "ModelErrorException",
            "InternalServerException",
            "ModelNotReadyException",
        }:
            return InvokeServerUnavailableError(error_msg)
        elif error_code == "ModelStreamErrorException":
            return InvokeConnectionError(error_msg)

        return InvokeError(error_msg)

    def _invoke_bedrock_embedding(
        self,
        model: str,
        bedrock_runtime,
        body: dict,
    ):
        accept = "application/json"
        content_type = "application/json"
        try:
            response = bedrock_runtime.invoke_model(
                body=json.dumps(body), modelId=model, accept=accept, contentType=content_type
            )
            response_body = json.loads(response.get("body").read().decode("utf-8"))
            return response_body
        except ClientError as ex:
            error_code = ex.response["Error"]["Code"]
            full_error_msg = f"{error_code}: {ex.response['Error']['Message']}"
            raise self._map_client_to_invoke_error(error_code, full_error_msg)

        except (EndpointConnectionError, NoRegionError, ServiceNotInRegionError) as ex:
            raise InvokeConnectionError(str(ex))

        except UnknownServiceError as ex:
            raise InvokeServerUnavailableError(str(ex))

        except Exception as ex:
            raise InvokeError(str(ex))
    
    def get_customizable_model_schema(self, model: str, credentials: dict) -> Optional[AIModelEntity]:
        """
        Get customizable model schema for inference profiles
        
        :param model: model name
        :param credentials: model credentials
        :return: AIModelEntity
        """
        inference_profile_id = credentials.get("inference_profile_id")
        if inference_profile_id:
            try:
                # Get inference profile info from AWS directly
                profile_info = get_inference_profile_info(inference_profile_id, credentials)
                
                # Extract model name from profile
                profile_name = profile_info.get("inferenceProfileName", model)
                context_length = int(credentials.get("context_length", 8192))
                
                # Find matching predefined model based on underlying model ARN
                default_pricing = None
                underlying_models = profile_info.get("models", [])
                if underlying_models:
                    first_model_arn = underlying_models[0].get("modelArn", "")
                    if "foundation-model/" in first_model_arn:
                        underlying_model_id = first_model_arn.split("foundation-model/")[1]
                        model_schemas = self.predefined_models()
                        for model_schema in model_schemas:
                            if model_schema.model == underlying_model_id:
                                default_pricing = model_schema.pricing
                                break
                
                # Fallback to first predefined model pricing if no match found
                if not default_pricing:
                    model_schemas = self.predefined_models()
                    if model_schemas:
                        default_pricing = model_schemas[0].pricing
                
                # Use the user-provided model name exactly as entered
                # Create custom model entity based on inference profile
                return AIModelEntity(
                    model=model,
                    label=I18nObject(en_US=model),
                    model_type=ModelType.TEXT_EMBEDDING,
                    features=[],
                    fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
                    model_properties={
                        "context_size": context_length,
                    },
                    parameter_rules=[],
                    pricing=default_pricing
                )
            except Exception as e:
                logger.error(f"Failed to get inference profile schema: {str(e)}")
                # Create fallback custom model entity with inference profile name
                context_length = int(credentials.get("context_length", 8192))
                model_schemas = self.predefined_models()
                default_pricing = model_schemas[0].pricing if model_schemas else None
                # Use the user-provided model name exactly as entered
                return AIModelEntity(
                    model=model,
                    label=I18nObject(en_US=model),
                    model_type=ModelType.TEXT_EMBEDDING,
                    features=[],
                    fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
                    model_properties={
                        "context_size": context_length,
                    },
                    parameter_rules=[],
                    pricing=default_pricing
                )
        else:
            # Not an inference profile, use regular model
            return None
    
    
    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            # Check if this is an inference profile based custom model
            inference_profile_id = credentials.get("inference_profile_id")
            if inference_profile_id:
                # Validate inference profile directly
                validate_inference_profile(inference_profile_id, credentials)
                logger.info(f"Successfully validated inference profile: {inference_profile_id}")
                return
            
            # Traditional model validation - invoke with a test text
            self._invoke(
                model=model,
                credentials=credentials,
                texts=["test"],
                user="test_user"
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))
    
