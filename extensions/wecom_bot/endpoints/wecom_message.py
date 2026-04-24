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
        
        logger.info(f"WeCom payload: {payload}")
        msgtype = payload.get("msgtype")
        
        def handle_poll(target_id: str) -> Response:
            try:
                state = self.session.storage.get(f"wecom_msg_state_{target_id}")
            except Exception:
                state = None
            state_str = state.decode("utf-8") if state else "done"
            
            try:
                content_bytes = self.session.storage.get(f"wecom_msg_content_{target_id}")
            except Exception:
                content_bytes = b""
            content_str = content_bytes.decode("utf-8") if content_bytes else ""
            
            if state_str == "processing":
                res = self._build_wecom_res(
                    message_id=target_id,
                    content=content_str,
                    finish=False,
                    timestamp=timestamp,
                    nonce=nonce,
                    cryptor=cryptor,
                )
            else:
                res = self._build_wecom_res(
                    message_id=target_id,
                    content=content_str,
                    finish=True,
                    timestamp=timestamp,
                    nonce=nonce,
                    cryptor=cryptor,
                )
                
                # Eagerly delete keys since processing is done
                try:
                    self.session.storage.delete(f"wecom_msg_state_{target_id}")
                    self.session.storage.delete(f"wecom_msg_content_{target_id}")
                except Exception:
                    pass
                    
                recent_ids_key = "wecom_recent_msgs"
                try:
                    recent_bytes = self.session.storage.get(recent_ids_key)
                    recent_ids = json.loads(recent_bytes.decode("utf-8")) if recent_bytes else []
                    if target_id in recent_ids:
                        recent_ids.remove(target_id)
                        self.session.storage.set(recent_ids_key, json.dumps(recent_ids).encode("utf-8"))
                except Exception:
                    pass
            
            return Response(status=200, response=res, mimetype="application/json")

        def safe_set(key: str, val: bytes):
            try:
                self.session.storage.set(key, val)
            except Exception as e:
                logger.warning(f"Storage safe_set error for {key}: {e}")


        if msgtype == "stream":
            stream_id = payload.get("stream", {}).get("id")
            if not stream_id:
                return Response(status=200, response="success")
            logger.info(f"Processing stream poll: {stream_id}")
            return handle_poll(stream_id)

        message_id = payload.get("msgid")
        if not message_id:
            return Response(status=200, response="success")

        content = str(payload.get("text", {}).get("content", "")).strip()
        if not content:
            return Response(status=200, response="success")

        if self.session.storage.exist(f"wecom_msg_state_{message_id}"):
            logger.info(f"Duplicate message detected/poll: {message_id}")
            return handle_poll(message_id)

        logger.info(f"Processing new message: {message_id}")
        
        # Ring buffer history cleanup to avoid storage leak
        recent_ids_key = "wecom_recent_msgs"
        try:
            recent_bytes = self.session.storage.get(recent_ids_key)
            recent_ids = json.loads(recent_bytes.decode("utf-8")) if recent_bytes else []
        except Exception:
            recent_ids = []
            
        if message_id not in recent_ids:
            recent_ids.append(message_id)
            while len(recent_ids) > 20: 
                old_id = recent_ids.pop(0)
                try:
                    self.session.storage.delete(f"wecom_msg_state_{old_id}")
                    self.session.storage.delete(f"wecom_msg_content_{old_id}")
                except Exception:
                    pass
            try:
                safe_set(recent_ids_key, json.dumps(recent_ids).encode("utf-8"))
            except Exception as e:
                logger.warning(f"Failed to update recent_ids to storage: {e}")

        safe_set(f"wecom_msg_state_{message_id}", b"processing")
        safe_set(f"wecom_msg_content_{message_id}", b"")

        try:
            app = settings.get("app")
            app_id = app.get("app_id") if app else ""
        except Exception:
            app_id = ""

        raw_from = payload.get("from")
        raw_chatid = payload.get("chatid")
        raw_aibotid = payload.get("aibotid")
        raw_chattype = payload.get("chattype")
        raw_userid = raw_from.get("userid") if isinstance(raw_from, Mapping) else None
        logger.info(
            "WeCom payload identities: userid=%r, chatid=%r, aibotid=%r, chattype=%r",
            raw_userid,
            raw_chatid,
            raw_aibotid,
            raw_chattype,
        )

        # Scope conversation by bot and single/group chat identity.
        conv_key = None
        if app_id and raw_aibotid:
            if raw_chattype == "group" and raw_chatid:
                conv_key = f"wecom_conv_{app_id}_{raw_aibotid}_{raw_chatid}"
            elif raw_chattype == "single" and raw_userid:
                conv_key = f"wecom_conv_{app_id}_{raw_aibotid}_{raw_userid}"
        
        conversation_id = None
        if conv_key and self.session.storage.exist(conv_key):
            conversation_id = self.session.storage.get(conv_key).decode("utf-8")

        def consume_stream():
            full_answer = ""
            try:
                response_generator = self.session.app.chat.invoke(
                    app_id=app_id,
                    query=content,
                    inputs={},
                    response_mode="streaming",
                    conversation_id=conversation_id,
                )
                for data in response_generator:
                    if data.get("event") in ("agent_message", "message"):
                        full_answer += data.get("answer", "")
                        safe_set(f"wecom_msg_content_{message_id}", full_answer.encode("utf-8"))
                        
                        conv_id = data.get("conversation_id")
                        if conv_id and conv_key:
                            safe_set(conv_key, conv_id.encode("utf-8"))
                            
                    elif data.get("event") == "message_end":
                        # Fallback for checking conversation_id in metadata
                        metadata = data.get("metadata", {})
                        if isinstance(metadata, dict):
                            conv_id = metadata.get("conversation_id")
                            if conv_id and conv_key:
                                safe_set(conv_key, conv_id.encode("utf-8"))
                        break
                    elif data.get("event") == "error":
                        error_msg = full_answer + f"\nError: {data.get('message', 'Unknown error')}"
                        safe_set(f"wecom_msg_content_{message_id}", error_msg.encode("utf-8"))
                        break
            except Exception as exc:
                logger.error(f"Stream consumption error: {exc}")
                error_msg = full_answer + f"\nErrors: {exc}"
                safe_set(f"wecom_msg_content_{message_id}", error_msg.encode("utf-8"))
            finally:
                safe_set(f"wecom_msg_state_{message_id}", b"done")

        # Run stream consumption in the request context to keep gRPC alive
        consume_stream()

        # Only Request 1 reaches here. Usually Request 1 is aborted by WeCom timeout,
        # but if it completes quickly, it returns properly.
        final_content_bytes = self.session.storage.get(f"wecom_msg_content_{message_id}")
        final_content = final_content_bytes.decode("utf-8") if final_content_bytes else ""
        
        res = self._build_wecom_res(
            message_id=message_id,
            content=final_content,
            finish=True,
            timestamp=timestamp,
            nonce=nonce,
            cryptor=cryptor,
        )
        return Response(status=200, response=res, mimetype="application/json")
