import threading
from urllib.request import urlopen
from queue import Queue
from typing import Any, Optional
from dashscope import MultiModalConversation
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
    InvokeError,
)
from dify_plugin.interfaces.model.tts_model import TTSModel
from models._common import _CommonTongyi, get_http_base_address


class TongyiText2SpeechModel(_CommonTongyi, TTSModel):
    """
    Model class for Tongyi Speech to text model.
    """

    def _invoke(
        self,
        model: str,
        tenant_id: str,
        credentials: dict,
        content_text: str,
        voice: str,
        user: Optional[str] = None,
    ) -> Any:
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
        if not voice or voice not in [
            d["value"] for d in self.get_tts_model_voices(model=model, credentials=credentials)
        ]:
            voice = self._get_model_default_voice(model, credentials)
        return self._tts_invoke_streaming(
            model=model, credentials=credentials, content_text=content_text, voice=voice
        )

    def validate_credentials(
        self, model: str, credentials: dict, user: Optional[str] = None
    ) -> None:
        """
        validate credentials text2speech model

        :param model: model name
        :param credentials: model credentials
        :param user: unique user id
        :return: text translated to audio file
        """
        try:
            self._tts_invoke_streaming(
                model=model,
                credentials=credentials,
                content_text="Hello Dify!",
                voice=self._get_model_default_voice(model, credentials),
            )
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _tts_invoke_streaming(
        self, model: str, credentials: dict, content_text: str, voice: str
    ) -> Any:
        """
        _tts_invoke_streaming text2speech model

        :param model: model name
        :param credentials: model credentials
        :param voice: model timbre
        :param content_text: text content to be translated
        :return: text translated to audio file
        """
        word_limit = self._get_model_word_limit(model, credentials)
        http_base_address = get_http_base_address(credentials)
        try:
            audio_queue: Queue = Queue()
            error_queue: Queue = Queue()

            def invoke_remote(content, m, api_key, wl, base_address):
                try:
                    if len(content) < wl:
                        sentences = [content]
                    else:
                        sentences = list(
                            self._split_text_into_sentences(org_text=content, max_length=wl)
                        )
                    for sentence in sentences:
                        response = MultiModalConversation.call(
                            model=m,
                            api_key=api_key,
                            text=sentence.strip(),
                            voice=voice,
                            stream=False,
                            base_address=base_address,
                        )
                        if response.status_code != 200:
                            error_msg = response.message or f"API error: {response.status_code}"
                            error_queue.put(InvokeBadRequestError(error_msg))
                            audio_queue.put(None)
                            return
                        if not response.output or not response.output.audio:
                            error_queue.put(InvokeBadRequestError("No audio in response"))
                            audio_queue.put(None)
                            return
                        audio_url = response.output.audio.get("url")
                        if not audio_url:
                            error_queue.put(InvokeBadRequestError("No audio URL in response"))
                            audio_queue.put(None)
                            return
                        try:
                            with urlopen(audio_url, timeout=30) as response:
                                audio_data = response.read()
                            audio_queue.put(audio_data)
                        except Exception as e:
                            error_queue.put(
                                InvokeBadRequestError(f"Failed to download audio: {str(e)}")
                            )
                            audio_queue.put(None)
                            return
                    audio_queue.put(None)
                except Exception as e:
                    error_queue.put(self._map_invoke_error(e))
                    audio_queue.put(None)

            threading.Thread(
                target=invoke_remote,
                args=(
                    content_text,
                    model,
                    credentials.get("dashscope_api_key"),
                    word_limit,
                    http_base_address,
                ),
                daemon=True,
            ).start()
            while True:
                audio = audio_queue.get()
                if audio is None:
                    if not error_queue.empty():
                        error = error_queue.get()
                        if error:
                            raise error
                    break
                yield audio
        except InvokeError:
            raise
        except Exception as ex:
            raise InvokeBadRequestError(str(ex))

    def _map_invoke_error(self, error: Exception) -> InvokeError:
        error_mapping = self._invoke_error_mapping
        for invoke_error_type, dashscope_errors in error_mapping.items():
            if isinstance(error, tuple(dashscope_errors)):
                return invoke_error_type(str(error))
        return InvokeBadRequestError(str(error))
