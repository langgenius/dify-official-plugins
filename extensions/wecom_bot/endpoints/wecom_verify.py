from __future__ import annotations

from typing import Mapping

from werkzeug import Request, Response

from dify_plugin import Endpoint

from utils.crypto import WeComCryptor


class WeComVerifyEndpoint(Endpoint):
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        token = settings.get("token")
        encoding_key = settings.get("encoding_aes_key")
        if not token or not encoding_key:
            return Response(status=400, response="missing token or encoding key")

        signature = r.args.get("msg_signature")
        timestamp = r.args.get("timestamp")
        nonce = r.args.get("nonce")
        echostr = r.args.get("echostr")
        if not all([signature, timestamp, nonce, echostr]):
            return Response(status=400, response="missing params")

        try:
            cryptor = WeComCryptor(token=token, encoding_aes_key=encoding_key)
            plain = cryptor.decrypt_echostr(signature=signature, timestamp=timestamp, nonce=nonce, echostr=echostr)
            return Response(status=200, response=plain)
        except Exception as exc:  # pragma: no cover - handshake validation
            return Response(status=400, response=str(exc))
