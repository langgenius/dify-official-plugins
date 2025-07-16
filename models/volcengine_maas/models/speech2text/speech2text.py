from typing import IO, Optional
from dify_plugin.entities.model import AIModelEntity, FetchFrom, I18nObject, ModelType
from enum import IntEnum
from dify_plugin.entities.model import (
    ModelPropertyKey,
)
from dify_plugin.errors.model import (
    CredentialsValidateFailedError,
    InvokeBadRequestError,
)
from dify_plugin.interfaces.model.openai_compatible.speech2text import (
    OAICompatSpeech2TextModel,
)
import gzip
import json
import uuid
import websocket
import ssl
import wave
from io import BytesIO


class SpeechProtocol(IntEnum):
    """
    Enum class for llm feature.
    """

    PROTOCOL_VERSION = 0b0001
    DEFAULT_HEADER_SIZE = 0b0001

    # Message Type:
    FULL_CLIENT_REQUEST = 0b0001
    AUDIO_ONLY_REQUEST = 0b0010
    FULL_SERVER_RESPONSE = 0b1001
    SERVER_ACK = 0b1011
    SERVER_ERROR_RESPONSE = 0b1111

    # Message Type Specific Flags
    NO_SEQUENCE = 0b0000  # no check sequence
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011
    NEG_SEQUENCE_1 = 0b0011

    # Message Serialization
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001

    # Message Compression
    NO_COMPRESSION = 0b0000
    GZIP = 0b0001


class VolcengineOpenAISpeech2TextModel(OAICompatSpeech2TextModel):
    def get_customizable_model_schema(
        self, model: str, credentials: dict
    ) -> Optional[AIModelEntity]:
        """
        used to define customizable model schema
        """
        entity = AIModelEntity(
            model=model,
            label=I18nObject(en_US=model, zh_Hans=model),
            fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
            model_type=ModelType.SPEECH2TEXT,
            model_properties={
                ModelPropertyKey.FILE_UPLOAD_LIMIT: 25,
                ModelPropertyKey.SUPPORTED_FILE_EXTENSIONS: "wav,pcm",
            },
            parameter_rules=[],
        )
        return entity

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
        return self._speech2text_invoke(model, credentials, file, user)

    def validate_credentials(self, model: str, credentials: dict) -> None:
        """
        Validate model credentials

        :param model: model name
        :param credentials: model credentials
        :return:
        """
        try:
            #TODO: add this demo file to sdk or use as base64
            audio_file_path = "models/volcengine_maas/models/speech2text/demo.wav"
            with open(audio_file_path, "rb") as audio_file:
                self._speech2text_invoke(model, credentials, audio_file)
        except Exception as ex:
            raise CredentialsValidateFailedError(str(ex))

    def _speech2text_invoke(
        self, model: str, credentials: dict, file: IO[bytes], user: Optional[str] = None
    ) -> str:
        """
        Invoke speech2text model

        :param model: model name
        :param credentials: model credentials
        :param file: audio file
        :return: text for given audio file
        """
        reqid = str(uuid.uuid4())
        ws_url = credentials["ws_url"]
        header = {}
        header["X-Api-Resource-Id"] = "volc.bigasr.sauc.duration"
        header["X-Api-Access-Key"] = credentials["access_key"]
        header["X-Api-App-Key"] = credentials["app_key"]
        header["X-Api-Request-Id"] = reqid
        audio_data = file.read()
        if self._judge_wav(audio_data):
            detected_format = "wav"
            nchannels, sampwidth, framerate, nframes, wav_len = self._read_wav_info(
                audio_data
            )
            size_per_sec = nchannels * sampwidth * framerate
            segment_size = int(size_per_sec * 100 / 1000)
        else:
            detected_format = "pcm"
            segment_size = int(16000 * 2 * 1 * 100 / 500)
        request_params = {
            "user": {
                "uid": user if user else reqid,
            },
            "audio": {
                "format": detected_format,
                "sample_rate": 16000,
                "bits": 16,
                "channel": 1,
                "codec": "raw",
            },
            "request": {"model_name": "bigmodel", "enable_punc": True},
        }
        payload_bytes = str.encode(json.dumps(request_params))
        payload_bytes = gzip.compress(payload_bytes)
        full_client_request = bytearray(
            self._generate_header(
                message_type_specific_flags=SpeechProtocol.POS_SEQUENCE
            )
        )
        full_client_request.extend(self._generate_before_payload(sequence=1))
        full_client_request.extend(
            (len(payload_bytes)).to_bytes(4, "big")
        )  # payload size(4 bytes)
        full_client_request.extend(payload_bytes)  # payload
        ws = websocket.create_connection(
            ws_url, header=header, sslopt={"cert_reqs": ssl.CERT_NONE}, timeout=300
        )
        try:
            # Send initial request
            ws.send_binary(full_client_request)
            res = ws.recv()
            result = self._parse_response(res)
            # Process audio chunks
            text = ""
            seq = 1
            for _, (chunk, last) in enumerate(
                self._slice_data(audio_data, segment_size), 1
            ):
                seq += 1
                if last:
                    seq = -seq
                payload_bytes = gzip.compress(chunk)
                audio_only_request = bytearray(
                    self._generate_header(
                        message_type=SpeechProtocol.AUDIO_ONLY_REQUEST,
                        message_type_specific_flags=SpeechProtocol.POS_SEQUENCE,
                    )
                )
                if last:
                    audio_only_request = bytearray(
                        self._generate_header(
                            message_type=SpeechProtocol.AUDIO_ONLY_REQUEST,
                            message_type_specific_flags=SpeechProtocol.NEG_WITH_SEQUENCE,
                        )
                    )
                audio_only_request.extend(self._generate_before_payload(sequence=seq))
                audio_only_request.extend(
                    (len(payload_bytes)).to_bytes(4, "big")
                )  # payload size(4 bytes)
                req_str = " ".join(format(byte, "02x") for byte in audio_only_request)
                audio_only_request.extend(payload_bytes)  # payload
                ws.send_binary(audio_only_request)
                res = ws.recv()
                result = self._parse_response(res)
                if "payload_msg" in result:
                    if "result" in result["payload_msg"]:
                        if "text" in result["payload_msg"]["result"]:
                            text = result["payload_msg"]["result"]["text"]
                    if "error" in result["payload_msg"]:
                        raise InvokeBadRequestError(result["payload_msg"]["error"])
            ws.close()
        except Exception as ex:
            ws.close()
            raise InvokeBadRequestError(str(ex))
        return text

    def _generate_header(
        self,
        message_type=SpeechProtocol.FULL_CLIENT_REQUEST,
        message_type_specific_flags=SpeechProtocol.NO_SEQUENCE,
        serial_method=SpeechProtocol.JSON,
        compression_type=SpeechProtocol.GZIP,
        reserved_data=0x00,
    ):
        """
        protocol_version(4 bits), header_size(4 bits),
        message_type(4 bits), message_type_specific_flags(4 bits)
        serialization_method(4 bits) message_compression(4 bits)
        reserved （8bits)
        """
        header = bytearray()
        header_size = 1
        header.append(((SpeechProtocol.PROTOCOL_VERSION) << 4) | header_size)
        header.append((message_type << 4) | message_type_specific_flags)
        header.append((serial_method << 4) | compression_type)
        header.append(reserved_data)
        return header

    def _generate_before_payload(self, sequence: int):
        before_payload = bytearray()
        before_payload.extend(sequence.to_bytes(4, "big", signed=True))  # sequence
        return before_payload

    def _judge_wav(self, ori_data):
        if len(ori_data) < 44:
            return False
        if ori_data[0:4] == b"RIFF" and ori_data[8:12] == b"WAVE":
            return True
        return False

    def _read_wav_info(self, data: bytes = None) -> (int, int, int, int, bytes):
        with BytesIO(data) as _f:
            wave_fp = wave.open(_f, "rb")
            nchannels, sampwidth, framerate, nframes = wave_fp.getparams()[:4]
            wave_bytes = wave_fp.readframes(nframes)
        return nchannels, sampwidth, framerate, nframes, wave_bytes

    def _parse_response(self, res):
        """
        protocol_version(4 bits), header_size(4 bits),
        message_type(4 bits), message_type_specific_flags(4 bits)
        serialization_method(4 bits) message_compression(4 bits)
        reserved （8bits)
        header_extensions
        payload
        """
        protocol_version = res[0] >> 4
        header_size = res[0] & 0x0F
        message_type = res[1] >> 4
        message_type_specific_flags = res[1] & 0x0F
        serialization_method = res[2] >> 4
        message_compression = res[2] & 0x0F
        reserved = res[3]
        header_extensions = res[4 : header_size * 4]
        payload = res[header_size * 4 :]
        result = {
            "is_last_package": False,
        }
        payload_msg = None
        payload_size = 0
        if message_type_specific_flags & 0x01:
            # receive frame with sequence
            seq = int.from_bytes(payload[:4], "big", signed=True)
            result["payload_sequence"] = seq
            payload = payload[4:]

        if message_type_specific_flags & 0x02:
            # receive last package
            result["is_last_package"] = True

        if message_type == SpeechProtocol.FULL_SERVER_RESPONSE:
            payload_size = int.from_bytes(payload[:4], "big", signed=True)
            payload_msg = payload[4:]
        elif message_type == SpeechProtocol.SERVER_ACK:
            seq = int.from_bytes(payload[:4], "big", signed=True)
            result["seq"] = seq
            if len(payload) >= 8:
                payload_size = int.from_bytes(payload[4:8], "big", signed=False)
                payload_msg = payload[8:]
        elif message_type == SpeechProtocol.SERVER_ERROR_RESPONSE:
            code = int.from_bytes(payload[:4], "big", signed=False)
            result["code"] = code
            payload_size = int.from_bytes(payload[4:8], "big", signed=False)
            payload_msg = payload[8:]
        if payload_msg is None:
            return result
        if message_compression == SpeechProtocol.GZIP:
            payload_msg = gzip.decompress(payload_msg)
        if serialization_method == SpeechProtocol.JSON:
            payload_msg = json.loads(str(payload_msg, "utf-8"))
        elif serialization_method != SpeechProtocol.NO_SERIALIZATION:
            payload_msg = str(payload_msg, "utf-8")
        result["payload_msg"] = payload_msg
        result["payload_size"] = payload_size
        return result

    def _slice_data(self, data: bytes, chunk_size: int) -> (list, bool):
        data_len = len(data)
        offset = 0
        while offset + chunk_size < data_len:
            yield data[offset : offset + chunk_size], False
            offset += chunk_size
        else:
            yield data[offset:data_len], True
