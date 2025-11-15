from __future__ import annotations

import json
import time
from typing import Any, Mapping

import requests
from werkzeug import Request, Response

from dify_plugin import Endpoint

from ..utils.crypto import WeComCryptor


class WeComEndpoint(Endpoint):
    _token_cache: dict[str, tuple[str, float]] = {}

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        method = r.method.upper()
        token = settings.get("token")
        encoding_key = settings.get("encoding_aes_key")
        receive_id = settings.get("receive_id")
        if not all([token, encoding_key, receive_id]):
            return Response(status=400, response="Missing WeCom credentials")

        cryptor = WeComCryptor(token=token, encoding_aes_key=encoding_key, receive_id=receive_id)

        args = r.args
        signature = args.get("msg_signature")
        timestamp = args.get("timestamp")
        nonce = args.get("nonce")

        if method == "GET":
            if not all([signature, timestamp, nonce, args.get("echostr")]):
                return Response(status=400, response="missing echostr params")
            try:
                plain = cryptor.decrypt_echostr(
                    signature=signature,
                    timestamp=timestamp,
                    nonce=nonce,
                    echostr=args.get("echostr"),
                )
            except Exception as exc:  # pragma: no cover - handshake guard
                return Response(status=400, response=str(exc))
            return Response(status=200, response=plain)

        try:
            data = r.get_json(force=True)
        except Exception as exc:
            return Response(status=400, response=f"invalid body: {exc}")

        encrypt = data.get("encrypt") if isinstance(data, Mapping) else None
        if not all([signature, timestamp, nonce, encrypt]):
            return Response(status=400, response="missing signature or encrypt field")

        try:
            payload = cryptor.decrypt(signature=signature, timestamp=timestamp, nonce=nonce, ciphertext=encrypt)
        except Exception as exc:
            return Response(status=400, response=f"decrypt_failed: {exc}")

        msg_type = str(payload.get("MsgType") or "").lower()
        if msg_type != "text":
            return Response(status=200, response="success")

        content = payload.get("Content") or ""
        if not content:
            return Response(status=200, response="success")

        from_user = payload.get("FromUserName")
        if not from_user:
            return Response(status=200, response="success")

        # Invoke configured Dify app/agent
        try:
            app = settings.get("app") or {}
            result = self.session.app.chat.invoke(
                app_id=app.get("app_id"),
                query=str(content),
                inputs={},
                response_mode="blocking",
            )
            answer = result.get("answer") or json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            return Response(status=200, response=f"error:{exc}")

        send_error = self._send_text(
            corp_id=settings.get("corp_id"),
            agent_secret=settings.get("agent_secret"),
            agent_id=settings.get("agent_id"),
            user_id=from_user,
            content=answer,
        )
        if send_error:
            return Response(status=200, response=f"error:{send_error}")
        return Response(status=200, response="success")

    def _send_text(
        self,
        *,
        corp_id: str | None,
        agent_secret: str | None,
        agent_id: str | None,
        user_id: str,
        content: str,
    ) -> str | None:
        if not corp_id or not agent_secret or not agent_id:
            return "missing corp/app credentials"
        access_token = self._get_access_token(corp_id=corp_id, agent_secret=agent_secret)
        if not access_token:
            return "unable to obtain access token"
        payload = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": agent_id,
            "text": {"content": content[:2048]},
            "safe": 0,
        }
        resp = requests.post(
            "https://qyapi.weixin.qq.com/cgi-bin/message/send",
            params={"access_token": access_token},
            json=payload,
            timeout=10,
        )
        try:
            data = resp.json()
        except Exception:
            return f"send_failed:{resp.text}"
        if data.get("errcode") != 0:
            return f"send_failed:{data}"
        return None

    def _get_access_token(self, *, corp_id: str, agent_secret: str) -> str | None:
        cache_key = f"{corp_id}:{agent_secret}"
        cached = self._token_cache.get(cache_key)
        now = time.time()
        if cached and cached[1] > now:
            return cached[0]
        try:
            resp = requests.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": corp_id, "corpsecret": agent_secret},
                timeout=10,
            )
            data = resp.json()
        except Exception:
            return None
        if data.get("errcode") != 0:
            return None
        expires_in = int(data.get("expires_in", 7200))
        token = data.get("access_token")
        if token:
            self._token_cache[cache_key] = (token, now + expires_in - 60)
        return token
