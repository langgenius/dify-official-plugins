import concurrent.futures
from typing import Any, Optional
from dify_plugin import TTSModel
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
from xinference_client.client.restful.restful_client import RESTfulAudioModelHandle
from models.xinference_helper import XinferenceHelper, validate_model_uid


class XinferenceText2SpeechModel(TTSModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_voices = {
            "__default": {"all": [{"name": "Default", "value": "default"}]},
            "ChatTTS": {
                "all": [
                    {"name": "Alloy", "value": "alloy"},
                    {"name": "Echo", "value": "echo"},
                    {"name": "Fable", "value": "fable"},
                    {"name": "Onyx", "value": "onyx"},
                    {"name": "Nova", "value": "nova"},
                    {"name": "Shimmer", "value": "shimmer"},
                ]
            },
            "CosyVoice": {
                "zh-Hans": [
                    {"name": "中文男", "value": "中文男"},
                    {"name": "中文女", "value": "中文女"},
                    {"name": "粤语女", "value": "粤语女"},
                ],
                "zh-Hant": [
                    {"name": "中文男", "value": "中文男"},
                    {"name": "中文女", "value": "中文女"},
                    {"name": "粤语女", "value": "粤语女"},
                ],
                "en-US": [
                    {"name": "英文男", "value": "英文男"},
                    {"name": "英文女", "value": "英文女"},
                ],
                "ja-JP": [{"name": "日语男", "value": "日语男"}],
                "ko-KR": [{"name": "韩语女", "value": "韩语女"}],
            },
        }

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
            credentials["server_url"] = credentials["server_url"].removesuffix("/")
            extra_param = XinferenceHelper.get_xinference_extra_parameter(
                server_url=credentials["server_url"],
                model_uid=credentials["model_uid"],
                api_key=credentials.get("api_key"),
            )
            if "text-to-audio" not in extra_param.model_ability:
                raise InvokeBadRequestError(
                    "please check model type, the model you want to invoke is not a text-to-audio model"
                )
            if (
                extra_param.model_family
                and extra_param.model_family in self.model_voices
            ):
                credentials["audio_model_name"] = extra_param.model_family
            else:
                credentials["audio_model_name"] = "__default"
            self._tts_invoke_streaming(
                model=model,
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ):
        """
        _invoke text2speech model

        :param model: model name
        :param tenant_id: user tenant id
        :param credentials: model credentials
        :param voice: model timbre
        :param content_text: text content to be translated
        :param user: unique user id
        :return: text translated to audio file
        """
        return self._tts_invoke_streaming(model, credentials, content_text, voice)

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
            model_type=ModelType.TTS,
            model_properties={},
            parameter_rules=[],
        )
        return entity

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

    def get_tts_model_voices(
        self, model: str, credentials: dict, language: Optional[str] = None
    ) -> list:
        audio_model_name = credentials.get("audio_model_name", "__default")
        for key, voices in self.model_voices.items():
            if key in audio_model_name:
                if language and language in voices:
                    return voices[language]
                elif "all" in voices:
                    return voices["all"]
                else:
                    all_voices = []
                    for lang, lang_voices in voices.items():
                        all_voices.extend(lang_voices)
                    return all_voices
        return self.model_voices["__default"]["all"]

    def _get_model_default_voice(self, model: str, credentials: dict) -> Any:
        return ""

    def _get_model_word_limit(self, model: str, credentials: dict) -> int:
        return 3500

    def _get_model_audio_type(self, model: str, credentials: dict) -> str:
        return "mp3"

    def _get_model_workers_limit(self, model: str, credentials: dict) -> int:
        return 5

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> Any:
        """
        _tts_invoke_streaming text2speech model

        :param model: model name
        :param credentials: model credentials
        :param content_text: text content to be translated
        :param voice: model timbre
        :return: text translated to audio file
        """
        credentials["server_url"] = credentials["server_url"].removesuffix("/")
        try:
            api_key = credentials.get("api_key")
            auth_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            handle = RESTfulAudioModelHandle(
                credentials["model_uid"],
                credentials["server_url"],
                auth_headers=auth_headers,
            )
            model_support_voice = [
                x.get("value")
                for x in self.get_tts_model_voices(model=model, credentials=credentials)
            ]
            if not voice or voice not in model_support_voice:
                voice = self._get_model_default_voice(model, credentials)
            word_limit = self._get_model_word_limit(model, credentials)
            if len(content_text) > word_limit:
                sentences = self._split_text_into_sentences(
                    content_text, max_length=word_limit
                )
                executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(3, len(sentences))
                )
                futures = [
                    executor.submit(
                        handle.speech,
                        input=sentences[i],
                        voice=voice,
                        response_format="mp3",
                        speed=1.0,
                        stream=True,
                    )
                    for i in range(len(sentences))
                ]
                for future in futures:
                    response = future.result()
                    for chunk in response:
                        yield chunk
            else:
                response = handle.speech(
                    input=content_text.strip(),
                    voice=voice,
                    response_format="mp3",
                    speed=1.0,
                    stream=True,
                )
                for chunk in response:
                    yield chunk
        except Exception as ex:
            raise InvokeBadRequestError(str(ex))
