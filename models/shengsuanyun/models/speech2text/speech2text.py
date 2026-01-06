from typing import IO, Optional
from openai import OpenAI

from dify_plugin import Speech2TextModel
from dify_plugin.errors.model import CredentialsValidateFailedError
from ..common_openai import _CommonOpenAI

class OpenAISpeech2TextModel(_CommonOpenAI, Speech2TextModel):
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
        # transform credentials to kwargs for model instance
        credentials_kwargs = self._to_credential_kwargs(credentials)

        # init model client
        client = OpenAI(**credentials_kwargs)

        response = client.audio.transcriptions.create(model=model, file=file)

        return response.text

     def _to_credential_kwargs(self, credentials: Mapping) -> dict:
        credentials_kwargs = {
            "api_key": credentials['api_key'],
            "timeout": Timeout(3150.0, read=3000.0, write=300.0, connect=200.0),
            "max_retries": 1,
        }
        credentials_kwargs["base_url"] = 'https://router.shengsuanyun.com/api/v1'
        if credentials.get("base_url"):
            api_base = credentials["base_url"].rstrip("/")
            # Don't append /v1 if it's already in the base_url
            if not api_base.endswith("/v1"):
                credentials_kwargs["base_url"] = api_base + "/v1"
            else:
                credentials_kwargs["base_url"] = api_base
        credentials_kwargs["default_headers"] = {
            "HTTP-Referer": "https://dify.ai",
            "X-Title": "Dify Plugin",
        }
        return credentials_kwargs
