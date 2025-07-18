from typing import IO, Optional

from dify_plugin import Speech2TextModel
import httpx
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError, InvokeError

from fish_audio_sdk import Session, ASRRequest

class FishAudioSpeech2TextModel(Speech2TextModel):
    """
    Model class for OpenAI Speech to text model.
    """
    def _invoke(self, model: str, credentials: dict,
                file: IO[bytes], user: Optional[str] = None) \
            -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        return self._speech2text_invoke(model, credentials, file)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            audio_file_path = self._get_demo_file_path()

            with open(audio_file_path, 'rb') as audio_file:
                self._speech2text_invoke(model, credentials, audio_file)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _speech2text_invoke(self, model: str, credentials: dict, file: IO[bytes]) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :return: text for given audio file
        """
        api_key = credentials.get("api_key")
        api_base= credentials.get("api_base")
        request = ASRRequest(
            audio=file.read(),
            ignore_timestamps=False
        )
        session = Session(api_key, base_url=api_base)
        return session.asr(request).text

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
            InvokeBadRequestError: [
                httpx.HTTPStatusError,
            ],
        }
