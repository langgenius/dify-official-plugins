import json
from typing import Mapping, Optional, Dict, Any, List
import requests
from werkzeug import Request, Response
from dify_plugin import Endpoint
from dify_plugin.invocations.app.chat import ChatAppInvocation


class WhatsappBotEndpoint(Endpoint):

    # ---------------------------
    # Public entry
    # ---------------------------
    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        if r.method == 'GET':
            return self._handle_verify(r, settings)
        if r.method != 'POST':
            return Response("Method Not Allowed", status=405, content_type="text/plain")
        return self._handle_webhook(r, settings)

    # ---------------------------
    # GET: Meta webhook verification
    # ---------------------------
    def _handle_verify(self, r: Request, settings: Mapping) -> Response:
        """
        Handle Meta webhook verification by echoing hub.challenge when token matches.
        """
        try:
            args = r.args or {}
            mode = (args.get('hub.mode') or args.get('mode') or '').strip()
            token = (args.get('hub.verify_token') or args.get('verify_token') or '').strip()
            challenge = args.get('hub.challenge')

            expected_token = (settings.get('verify_token') or '').strip()

            if mode == 'subscribe' and expected_token and token == expected_token and challenge is not None:
                return Response(str(challenge), status=200, content_type='text/plain')

            return Response('Forbidden', status=403, content_type='text/plain')
        except Exception:
            return Response('Forbidden', status=403, content_type='text/plain')

    # ---------------------------
    # Helpers
    # ---------------------------
    def _extract_text(self, message: Mapping) -> Optional[str]:

        if (message.get('type') or '').lower() != 'text':
            return None
        text = message.get('text') or {}
        body = text.get('body')
        return str(body) if body is not None else None

    def _get_app_id(self, app_setting) -> Optional[str]:

        if not app_setting:
            return None
        if isinstance(app_setting, str):
            app_id = app_setting.strip()
            return app_id or None
        if isinstance(app_setting, Mapping):
            app_id = (app_setting.get('app_id') or app_setting.get('id') or '').strip()  # type: ignore
            return app_id or None
        return None

    def _ok(self) -> Response:
        return Response("ok", status=200, content_type="text/plain")

    def _json_response(self, data: dict, status: int = 200) -> Response:
        return Response(
            json.dumps(data, ensure_ascii=False),
            status=status,
            content_type="application/json"
        )

    # ---------------------------
    # Dify invocation + conversation handling
    # ---------------------------
    def _invoke_app_reply(
        self,
        *,
        app_id: str,
        query: str,
        identify_inputs: Mapping[str, Any],
        conversation_key: str,
    ) -> Optional[str]:

        conversation_id: Optional[str] = None
        try:
            raw = self.session.storage.get(conversation_key)
            if raw:
                conversation_id = raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else str(raw)
        except Exception:
            conversation_id = None

        invoker = ChatAppInvocation(self.session)
        invoke_params: Dict[str, Any] = {
            "app_id": app_id,
            "query": query,
            "inputs": dict(identify_inputs),
            "response_mode": "blocking",
        }
        if conversation_id:
            invoke_params["conversation_id"] = conversation_id

        result: Dict[str, Any] = invoker.invoke(**invoke_params)

        answer = result.get("answer") or result.get("output_text") or result.get("message")
        new_conversation_id = result.get("conversation_id")
        if new_conversation_id:
            try:
                self.session.storage.set(conversation_key, str(new_conversation_id).encode("utf-8"))
            except Exception:
                pass

        return str(answer) if answer is not None else None

    # ---------------------------
    # WhatsApp sending
    # ---------------------------
    def _send_whatsapp_text(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        to_wa_id: str,
        body_text: str,
    ) -> None:

        url = f"https://graph.facebook.com/v24.0/{phone_number_id}/messages"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        data = {
            'messaging_product': 'whatsapp',
            'to': to_wa_id,
            'type': 'text',
            'text': {'body': body_text},
        }
        try:
            requests.post(url, headers=headers, data=json.dumps(data), timeout=10)
        except Exception:
            # 静默失败，依赖上游日志
            pass

    # ---------------------------
    # POST: Webhook handling
    # ---------------------------
    def _handle_webhook(self, r: Request, settings: Mapping) -> Response:

        try:
            payload = r.get_json(silent=True) or {}
        except Exception:
            return Response("Bad Request", status=400, content_type="text/plain")

        access_token = (settings.get('access_token') or '').strip()
        phone_number_id = (settings.get('phone_number_id') or '').strip()
        app_id = self._get_app_id(settings.get('app'))

        if not payload or 'entry' not in payload:
            return self._ok()

        can_reply = bool(access_token and phone_number_id)
        processed_messages: List[Dict[str, Any]] = []

        try:
            for entry in payload.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value') or {}
                    messages = value.get('messages') or []
                    if not messages:
                        continue

                    # 取 canonical wa_id（优先 contacts.0.wa_id）
                    contacts = value.get('contacts') or []
                    wa_id = None
                    if isinstance(contacts, list) and contacts:
                        contact0 = contacts[0] or {}
                        wa_id = contact0.get('wa_id')

                    metadata = value.get('metadata') or {}
                    display_phone_number = metadata.get('display_phone_number')
                    business_phone_number_id = metadata.get('phone_number_id') or phone_number_id

                    for message in messages:
                        # 仅处理 type == text
                        text_body = self._extract_text(message)
                        if text_body is None:
                            continue

                        # 发送者 ID：优先 contacts.wa_id，其次 messages.from
                        sender_wa_id = str(wa_id or message.get('from') or '').strip()
                        if not sender_wa_id:
                            continue

                        message_id = message.get('id')
                        timestamp = message.get('timestamp')

                        # 构造 identify_inputs（与 LINE 逻辑一致：收集识别信息）
                        identify_inputs = {
                            'whatsapp_user_id': sender_wa_id,
                            'wa_id': sender_wa_id,
                            'message_id': message_id or '',
                            'timestamp': timestamp or '',
                            'phone_number_id': business_phone_number_id,
                        }

                        # 构造会话 key：按“业务号码 + 用户”隔离
                        conversation_key = f"whatsapp:{business_phone_number_id}:{sender_wa_id}"

                        # 命令：/clearconversationhistory
                        if text_body.strip().lower() == '/clearconversationhistory':
                            try:
                                self.session.storage.delete(conversation_key)
                            except Exception:
                                pass

                            if can_reply:
                                self._send_whatsapp_text(
                                    access_token=access_token,
                                    phone_number_id=business_phone_number_id,
                                    to_wa_id=sender_wa_id,
                                    body_text="SYSTEM: Session history in Dify cleared.",
                                )

                            processed_messages.append({
                                'wa_id': sender_wa_id,
                                'message_id': message_id,
                                'timestamp': timestamp,
                                'message_type': 'text',
                                'message_text': text_body,
                                'business_phone_number': display_phone_number,
                                'reply_sent': can_reply,
                                'reply_text': "SYSTEM: Session history in Dify cleared." if can_reply else None,
                                'cleared': True,
                            })
                            # 对该条命令不再调用 Dify
                            continue

                        # 调用 Dify 应用
                        reply_text: Optional[str] = None
                        if app_id:
                            reply_text = self._invoke_app_reply(
                                app_id=app_id,
                                query=text_body,
                                identify_inputs=identify_inputs,
                                conversation_key=conversation_key,
                            )

                        # 回复用户（如可）
                        reply_sent = False
                        if can_reply and reply_text:
                            self._send_whatsapp_text(
                                access_token=access_token,
                                phone_number_id=business_phone_number_id,
                                to_wa_id=sender_wa_id,
                                body_text=reply_text,
                            )
                            reply_sent = True

                        processed_messages.append({
                            'wa_id': sender_wa_id,
                            'message_id': message_id,
                            'timestamp': timestamp,
                            'message_type': 'text',
                            'message_text': text_body,
                            'business_phone_number': display_phone_number,
                            'reply_sent': reply_sent,
                            'reply_text': reply_text,
                        })

        except Exception as e:
            # 返回 JSON 方便排查（保持 200，避免平台重试风暴）
            return self._json_response({
                'status': 'error',
                'error': str(e),
                'processed_messages': processed_messages,
            }, status=200)

        # 返回详细处理结果
        return self._json_response({
            'status': 'success',
            'processed_messages': processed_messages,
            'total_processed': len(processed_messages),
        })
