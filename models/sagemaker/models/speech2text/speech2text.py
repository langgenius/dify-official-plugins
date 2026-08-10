import json
import logging
from typing import IO, Optional

from provider.sagemaker import buffer_to_s3, get_sagemaker_client

from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelType
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from dify_plugin import Speech2TextModel

logger = logging.getLogger(__name__)


class SageMakerSpeech2TextModel(Speech2TextModel):
    """
    Model class for Xinference speech to text model.
    """

    def _invoke(
        self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None
    ) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        asr_text = None

        try:
            s3_client = get_sagemaker_client("s3", credentials)
            sagemaker_client = get_sagemaker_client("sagemaker-runtime", credentials)

            s3_prefix = "dify/speech2text/"
            sagemaker_endpoint = credentials.get("sagemaker_endpoint")
            bucket = credentials.get("audio_s3_cache_bucket")

            if bucket:
                # For FunASR Model
                object_key = buffer_to_s3(s3_client, file, bucket, s3_prefix)
                payload = {"bucket_name": bucket, "s3_key": object_key}
                # s3_presign_url = generate_presigned_url(s3_client, file, bucket, s3_prefix)
                # payload = {"audio_s3_presign_uri": s3_presign_url}
                response_model = sagemaker_client.invoke_endpoint(
                    EndpointName=sagemaker_endpoint,
                    Body=json.dumps(payload),
                    ContentType="application/json",
                )
                json_str = response_model["Body"].read().decode("utf8")
                json_obj = json.loads(json_str)
                asr_text = json_obj["text"]
            else:
                # For Whisper Model
                resp = sagemaker_client.invoke_endpoint(
                    EndpointName=sagemaker_endpoint,
                    Body=file.read(),
                    ContentType="audio/x-audio",
                )
                json_obj = json.loads(resp["Body"].read().decode("utf8"))
                asr_text = json_obj["text"]

        except Exception as e:
            logger.exception(f"failed to invoke speech2text model, model: {model}")
            raise CredentialsValidateFailedError(str(e))

        return asr_text

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        pass

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
            InvokeConnectionError: [InvokeConnectionError],
            InvokeServerUnavailableError: [InvokeServerUnavailableError],
            InvokeRateLimitError: [InvokeRateLimitError],
            InvokeAuthorizationError: [InvokeAuthorizationError],
            InvokeBadRequestError: [InvokeBadRequestError, KeyError, ValueError],
        }

    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        used to define customizable model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_us=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={},
            parameter_rules=[],
        )

        return entity
