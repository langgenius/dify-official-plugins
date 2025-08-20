from typing import Optional
import logging

from botocore.exceptions import ClientError

from dify_plugin.entities.model.rerank import RerankDocument, RerankResult
from dify_plugin.interfaces.model.rerank_model import RerankModel
from dify_plugin.entities.model import AIModelEntity, FetchFrom, ModelType
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

from provider.get_bedrock_client import get_bedrock_client
from . import model_ids
from utils.inference_profile import (
    get_inference_profile_info,
    validate_inference_profile,
    extract_model_info_from_profile
)

logger = logging.getLogger(__name__)


class BedrockRerankModel(RerankModel):
    """
    Model class for Cohere rerank model.
    """

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
        Invoke rerank model

        :param model: model name
        :param credentials: model credentials
        :param query: search query
        :param docs: docs for reranking
        :param score_threshold: score threshold
        :param top_n: top n
        :param user: unique user id
        :return: rerank result
        """

        if len(docs) == 0:
            return RerankResult(model=model, docs=docs)

        # initialize client
        bedrock_runtime = get_bedrock_client("bedrock-agent-runtime", credentials)
        queries = [{"type": "TEXT", "textQuery": {"text": query}}]
        text_sources = []
        for text in docs:
            text_sources.append(
                {
                    "type": "INLINE",
                    "inlineDocumentSource": {
                        "type": "TEXT",
                        "textDocument": {
                            "text": text,
                        },
                    },
                }
            )
        # Check if using inference profile
        model_id = model
        inference_profile_id = credentials.get("inference_profile_id")
        if inference_profile_id:
            # Get the full ARN from the profile ID
            profile_info = get_inference_profile_info(inference_profile_id, credentials)
            model_package_arn = profile_info.get("inferenceProfileArn")
            if not model_package_arn:
                raise InvokeError(f"Could not get ARN for inference profile {inference_profile_id}")
            logger.info(f"Using inference profile ARN: {model_package_arn}")
        else:
            # Traditional model - build ARN
            region = credentials.get("aws_region")
            # region is a required field
            if not region:
                raise InvokeBadRequestError("aws_region is required in credentials")
            model_package_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
        rerankingConfiguration = {
            "type": "BEDROCK_RERANKING_MODEL",
            "bedrockRerankingConfiguration": {
                "numberOfResults": min(len(text_sources) if top_n is None else top_n, len(text_sources)),
                "modelConfiguration": {
                    "modelArn": model_package_arn,
                },
            },
        }
        response = bedrock_runtime.rerank(
            queries=queries, sources=text_sources, rerankingConfiguration=rerankingConfiguration
        )

        rerank_documents = []
        for idx, result in enumerate(response["results"]):
            # format document
            index = result["index"]
            rerank_document = RerankDocument(
                index=index,
                text=docs[index],
                score=result["relevanceScore"],
            )

            # score threshold check
            if score_threshold is not None:
                if rerank_document.score >= score_threshold:
                    rerank_documents.append(rerank_document)
            else:
                rerank_documents.append(rerank_document)

        return RerankResult(model=model, docs=rerank_documents)
    
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
                context_length = int(credentials.get("context_length", 5120))
                
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
                    model_type=ModelType.RERANK,
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
                context_length = int(credentials.get("context_length", 5120))
                model_schemas = self.predefined_models()
                default_pricing = model_schemas[0].pricing if model_schemas else None
                # Use the user-provided model name exactly as entered
                return AIModelEntity(
                    model=model,
                    label=I18nObject(en_US=model),
                    model_type=ModelType.RERANK,
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
            
            # Traditional model validation - check if we can get bedrock client
            bedrock_runtime = get_bedrock_client("bedrock-agent-runtime", credentials)
            # Just getting the client validates the credentials
            logger.info(f"Successfully validated model: {model}")
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))
    

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            self.invoke(
                model=model,
                credentials=credentials,
                query="What is the capital of the United States?",
                docs=[
                    "Carson City is the capital city of the American state of Nevada. At the 2010 United States "
                    "Census, Carson City had a population of 55,274.",
                    "The Commonwealth of the Northern Mariana Islands is a group of islands in the Pacific Ocean that "
                    "are a political division controlled by the United States. Its capital is Saipan.",
                ],
                score_threshold=0.8,
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

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
