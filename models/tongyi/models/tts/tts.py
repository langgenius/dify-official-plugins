import threading
from queue import Queue
from typing import Any, Optional
from dashscope import SpeechSynthesizer
from dashscope.api_entities.dashscope_response import SpeechSynthesisResponse
from dashscope.audio.tts import ResultCallback, SpeechSynthesisResult
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeBadRequestError
from dify_plugin.interfaces.model.tts_model import TTSModel
from models._common import _CommonTongyi, get_ws_base_address
from ..constant import BURY_POINT_HEADER

class TongyiText2SpeechModel(_CommonTongyi, TTSModel):
    """
    Model class for Tongyi Speech to text model.
    """

    def _invoke(
        self, model: str, tenant_id: str, credentials: dict, content_text: str, voice: str, user: Optional[str] = None
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
        return self._tts_invoke_streaming(model=model, credentials=credentials, content_text=content_text, voice=voice)

    def validate_credentials(self, model: str, credentials: dict, user: Optional[str] = None) -> None:
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

    def _tts_invoke_streaming(self, model: str, credentials: dict, content_text: str, voice: str) -> Any:
        """
        _tts_invoke_streaming text2speech model

        :param model: model name
        :param credentials: model credentials
        :param voice: model timbre
        :param content_text: text content to be translated
        :return: text translated to audio file
        """
        word_limit = self._get_model_word_limit(model, credentials)
        audio_type = self._get_model_audio_type(model, credentials)
        ws_base_address = get_ws_base_address(credentials)
        try:
            audio_queue: Queue = Queue()
            failure_event = threading.Event()
            callback = Callback(queue=audio_queue, failure_event=failure_event)

            def invoke_remote(content, v, api_key, cb, at, wl, base_address):
                try:
                    if len(content) < word_limit:
                        sentences = [content]
                    else:
                        sentences = list(self._split_text_into_sentences(org_text=content, max_length=wl))
                    for sentence in sentences:
                        if failure_event.is_set():
                            # A previous sentence failed; skip the rest to save API quota.
                            break
                        SpeechSynthesizer.call(
                            model=v,
                            sample_rate=16000,
                            api_key=api_key,
                            text=sentence.strip(),
                            callback=cb,
                            format=at,
                            headers=BURY_POINT_HEADER,
                            word_timestamp_enabled=True,
                            phoneme_timestamp_enabled=True,
                            base_address=base_address,
                        )
                finally:
                    # End-of-stream sentinel is emitted here (not in on_complete), so that
                    # multi-sentence synthesis is not terminated after the first sentence.
                    audio_queue.put(None)

            threading.Thread(
                target=invoke_remote,
                args=(
                    content_text,
                    voice,
                    credentials.get("dashscope_api_key"),
                    callback,
                    audio_type,
                    word_limit,
                    ws_base_address,
                ),
            ).start()
            while True:
                audio = audio_queue.get()
                if audio is None:
                    break
                yield audio
        except Exception as ex:
            raise InvokeBadRequestError(str(ex))

    @staticmethod
    def _process_sentence(sentence: str, credentials: dict, voice: str, audio_type: str):
        """
        _tts_invoke Tongyi text2speech model api

        :param credentials: model credentials
        :param sentence: text content to be translated
        :param voice: model timbre
        :param audio_type: audio file type
        :return: text translated to audio file
        """
        ws_base_address = get_ws_base_address(credentials)
        response = SpeechSynthesizer.call(
            model=voice,
            sample_rate=48000,
            api_key=credentials.get("dashscope_api_key"),
            text=sentence.strip(),
            headers=BURY_POINT_HEADER,
            format=audio_type,
            base_address=ws_base_address,
        )
        if isinstance(response.get_audio_data(), bytes):
            return response.get_audio_data()


class Callback(ResultCallback):
    def __init__(self, queue: Queue, failure_event: threading.Event):
        self._queue = queue
        self._failure_event = failure_event

    def on_open(self):
        pass

    def on_complete(self):
        # Each SpeechSynthesizer.call() fires on_complete per sentence; the end-of-stream
        # sentinel is emitted by the producer thread after the last sentence, so that
        # multi-sentence text is not cut off after the first sentence.
        pass

    def on_error(self, response: SpeechSynthesisResponse):
        # Signal the producer to stop; the end-of-stream sentinel is emitted by the
        # producer's finally block so the queue never contains duplicate sentinels.
        self._failure_event.set()

    def on_close(self):
        # See on_complete: do not terminate the stream on a single sentence completing.
        pass

    def on_event(self, result: SpeechSynthesisResult):
        ad = result.get_audio_frame()
        if ad:
            self._queue.put(ad)
