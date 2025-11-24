import logging
import json
from typing import Mapping

from werkzeug import Request, Response
from dify_plugin import Endpoint
from dify_plugin.config.logger_format import plugin_logger_handler

from utils.crypto import WeComCryptor


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(plugin_logger_handler)


class WeComMessageEndpoint(Endpoint):
    def _build_wecom_res(self, message_id: str, content: str, finish: bool, timestamp: str, nonce: str, cryptor: WeComCryptor) -> str:
        body = {
            "msgtype": "stream",
            "stream": {
                "id": message_id,
                "finish": finish,
                "content": content,
            }
        }

        encrypted = cryptor.encrypt_response(
                plain=json.dumps(body, ensure_ascii=False),
                timestamp=timestamp,
                nonce=nonce,
        )
        return json.dumps(encrypted, ensure_ascii=False)

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        token = settings.get("token")
        encoding_key = settings.get("encoding_aes_key")
        if not token or not encoding_key:
            return Response(status=400, response="missing token or encoding key")

        signature = r.args.get("msg_signature")
        timestamp = r.args.get("timestamp")
        nonce = r.args.get("nonce")
        if not all([signature, timestamp, nonce]):
            return Response(status=400, response="missing signature params")

        try:
            body = r.get_json(force=True)
        except Exception as exc:
            return Response(status=400, response=f"invalid json: {exc}")

        encrypt = body.get("encrypt") if isinstance(body, Mapping) else None
        if not encrypt:
            return Response(status=400, response="missing encrypt")

        cryptor = WeComCryptor(token=token, encoding_aes_key=encoding_key)
        try:
            payload = cryptor.decrypt(signature=signature, timestamp=timestamp, nonce=nonce, ciphertext=encrypt)
        except Exception as exc:
            return Response(status=400, response=f"decrypt_failed:{exc}")
        
        content = str(payload.get("text", {}).get("content")).strip()
        if not content:
            return Response(status=200, response="success")
        
        message_id = payload.get("msgid")
        if self.session.storage.exist(f"wecom_msg_{message_id}"):
            logger.info(f"Duplicate message detected: {message_id}")
            res = self._build_wecom_res(
                message_id=message_id,
                content="",
                finish=False,
                timestamp=timestamp,
                nonce=nonce,
                cryptor=cryptor,
            )
            return Response(status=200, response=res, mimetype="application/json")
        else:
            logger.info(f"Processing new message: {message_id}")
            self.session.storage.set(f"wecom_msg_{message_id}", b"processing")
        
        if payload.get("msgtype") == "stream":
            stream_id = payload.get("stream", {}).get("id") 
            if self.session.storage.exist(f"wecom_msg_{stream_id}"):
                logger.info(f"Duplicate stream detected: {stream_id}")

                result = self.session.storage.get(f"wecom_msg_{stream_id}").decode()
                if result == "processing":
                    res = self._build_wecom_res(
                        message_id=stream_id,
                        content="",
                        finish=False,
                        timestamp=timestamp,
                        nonce=nonce,
                        cryptor=cryptor,
                    )
                else:
                    res = self._build_wecom_res(
                        message_id=stream_id,
                        content=result,
                        finish=True,
                        timestamp=timestamp,
                        nonce=nonce,
                        cryptor=cryptor,
                    )
                    self.session.storage.delete(f"wecom_msg_{stream_id}")
                return Response(status=200, response=res, mimetype="application/json")
            else:
                logger.info(f"Processing new stream: {stream_id}")
                self.session.storage.set(f"wecom_msg_{stream_id}", b"processing")

        try:
            app = settings.get("app")
            response = self.session.app.chat.invoke(
                app_id=app.get("app_id"),
                query=content,
                inputs={},
                response_mode="blocking",
            )
            answer = response.get("answer") or json.dumps(response, ensure_ascii=False)
        except Exception as exc:
            answer = f"Errors：{exc}"
        
        if len(answer) > 5000:
            answer = answer[:5000] + "..."

        stream_id = message_id
        self.session.storage.set(f"wecom_msg_{stream_id}", answer.encode())
        res = self._build_wecom_res(
            message_id=stream_id,
            content=answer,
            finish=True,
            timestamp=timestamp,
            nonce=nonce,
            cryptor=cryptor,
        )
        return Response(status=200, response=res, mimetype="application/json")
