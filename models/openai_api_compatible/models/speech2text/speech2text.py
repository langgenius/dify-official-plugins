from typing import IO,Optional
from urllib.parse import urljoin
from dify_plugin.errors.model import InvokeBadRequestError
import requests
from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelType
from dify_plugin.interfaces.model.openai_compatible.speech2text import OAICompatSpeech2TextModel


class OpenAISpeech2TextModel(OAICompatSpeech2TextModel):
    def _invoke(self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :param user: unique user id
        :return: text for given audio file
        """
        headers = {}

        api_key = credentials.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        endpoint_url = credentials.get("endpoint_url", "https://api.openai.com/v1/")
        if not endpoint_url.endswith("/"):
            endpoint_url += "/"
        endpoint_url = urljoin(endpoint_url, "audio/transcriptions")

        payload = {"model": credentials.get("endpoint_model_name", model)}
        # `language` and `prompt` are optional in the OpenAI transcription API and both
        # change the output, so only forward them when the user actually configured one.
        # Sending a hardcoded default made every request claim a language the server may
        # not support, and injected an unrelated English instruction as the decoder prompt.
        language = credentials.get("language")
        if language:
            payload["language"] = language
        prompt = credentials.get("initial_prompt")
        if prompt:
            payload["prompt"] = prompt

        files = [("file", file)]
        response = requests.post(
            endpoint_url,
            headers=headers,
            data=payload,
            files=files,
            timeout=(10, 300),
        )

        if response.status_code != 200:
            raise InvokeBadRequestError(response.text)
        response_data = response.json()
        return response_data["text"]

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

        if "display_name" in credentials and credentials["display_name"] != "":
            entity.label = I18nObject(
                en_us=credentials["display_name"], zh_hans=credentials["display_name"]
            )

        return entity
