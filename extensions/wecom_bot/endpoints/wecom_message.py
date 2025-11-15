from __future__ import annotations

import json
from typing import Mapping

from werkzeug import Request, Response

from dify_plugin import Endpoint

from utils.crypto import WeComCryptor


class WeComMessageEndpoint(Endpoint):
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

        plain = {
            "msgtype": "stream",
            "stream": {
                "id": "STREAMID",
                "finish": True,
                "content": answer,
            }
        }
        
        encrypted = cryptor.encrypt_response(
            plain=json.dumps(plain, ensure_ascii=False),
            timestamp=timestamp,
            nonce=nonce,
        )
        return Response(status=200, response=json.dumps(encrypted, ensure_ascii=False), mimetype="application/json")
