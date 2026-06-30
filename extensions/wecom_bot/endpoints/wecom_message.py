import base64
import logging
import json
from typing import Mapping

import requests
from werkzeug import Request, Response
from dify_plugin import Endpoint
from dify_plugin.config.logger_format import plugin_logger_handler
from Cryptodome.Cipher import AES

from utils.crypto import WeComCryptor


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
logger.addHandler(plugin_logger_handler)


def _decrypt_wecom_file(encrypted_bytes: bytes, encoding_aes_key: str) -> bytes:
    """Decrypt WeCom downloaded file with the callback EncodingAESKey (AES-256-CBC, PKCS7 padding, IV = first 16 bytes of key)."""
    key = base64.b64decode(encoding_aes_key + "=")
    iv = key[:16]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted = cipher.decrypt(encrypted_bytes)
    # PKCS7 unpad
    pad_len = decrypted[-1]
    return decrypted[:-pad_len]


def _download_and_decrypt_image(url: str, encoding_aes_key: str) -> bytes:
    """Download WeCom image and decrypt it, returning raw image bytes."""
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return _decrypt_wecom_file(resp.content, encoding_aes_key)


def _parse_quote(quote: Mapping, encoding_aes_key: str) -> tuple[list[str], list[bytes]]:
    """
    Parse the quoted message inside the `quote` field.
    Returns (list of text fragments, list of image bytes).
    """
    text_parts: list[str] = []
    images: list[bytes] = []

    quote_msgtype = quote.get("msgtype", "")
    if quote_msgtype == "text":
        quoted = str(quote.get("text", {}).get("content", "")).strip()
        if quoted:
            text_parts.append(f"【引用】{quoted}")
    elif quote_msgtype == "image":
        url = quote.get("image", {}).get("url", "")
        if url:
            try:
                img_bytes = _download_and_decrypt_image(url, encoding_aes_key)
                images.append(img_bytes)
                text_parts.append("【引用】[图片]")
            except Exception as exc:
                logger.debug(f"Failed to download/decrypt quoted image: {exc}")
                text_parts.append("【引用】[图片下载失败]")
    elif quote_msgtype == "mixed":
        quote_texts: list[str] = []
        for idx, item in enumerate(quote.get("mixed", {}).get("msg_item", [])):
            item_type = item.get("msgtype", "")
            if item_type == "text":
                part = str(item.get("text", {}).get("content", "")).strip()
                if part:
                    quote_texts.append(part)
            elif item_type == "image":
                url = item.get("image", {}).get("url", "")
                if not url:
                    continue
                try:
                    img_bytes = _download_and_decrypt_image(url, encoding_aes_key)
                    images.append(img_bytes)
                    quote_texts.append("[图片]")
                except Exception as exc:
                    logger.debug(f"Failed to download/decrypt quoted mixed image[{idx}]: {exc}")
                    quote_texts.append("[图片下载失败]")
        if quote_texts:
            text_parts.append(f"【引用】{' '.join(quote_texts)}")
    elif quote_msgtype in ("voice", "file", "video"):
        text_parts.append(f"【引用】[{quote_msgtype}]")

    return text_parts, images


def _parse_message(payload: Mapping, encoding_aes_key: str) -> tuple[str, list[bytes]]:
    """
    Parse WeCom message, returning (query text, list of image bytes).
    Supports text, image, mixed, quote message types.
    The quote field can be attached to text/image/mixed messages.
    """
    msgtype = payload.get("msgtype", "")
    text_parts: list[str] = []
    images: list[bytes] = []

    # ── Plain text ─────────────────────────────────────────
    if msgtype == "text":
        text = str(payload.get("text", {}).get("content", "")).strip()
        if text:
            text_parts.append(text)

    # ── Plain image ────────────────────────────────────────
    elif msgtype == "image":
        url = payload.get("image", {}).get("url", "")
        if url:
            try:
                img_bytes = _download_and_decrypt_image(url, encoding_aes_key)
                images.append(img_bytes)
            except Exception as exc:
                logger.debug(f"Failed to download/decrypt image: {exc}")
                text_parts.append("[图片下载失败]")

    # ── Mixed text + image ─────────────────────────────────
    elif msgtype == "mixed":
        for idx, item in enumerate(payload.get("mixed", {}).get("msg_item", [])):
            item_type = item.get("msgtype", "")
            if item_type == "text":
                part = str(item.get("text", {}).get("content", "")).strip()
                if part:
                    text_parts.append(part)
            elif item_type == "image":
                url = item.get("image", {}).get("url", "")
                if not url:
                    continue
                try:
                    img_bytes = _download_and_decrypt_image(url, encoding_aes_key)
                    images.append(img_bytes)
                except Exception as exc:
                    logger.debug(f"Failed to download/decrypt mixed image[{idx}]: {exc}")

    # ── Quote-only message (main body has no content) ──────
    elif msgtype == "quote":
        # When msgtype=quote, the main text may also exist in text.content
        main_text = str(payload.get("text", {}).get("content", "")).strip()
        if main_text:
            text_parts.append(main_text)

    # ── Other types are ignored ────────────────────────────
    else:
        return "", []

    # ── Attached quote field (text/image/mixed/quote may all carry it) ──
    quote = payload.get("quote")
    if quote and isinstance(quote, Mapping):
        qt, qi = _parse_quote(quote, encoding_aes_key)
        text_parts.extend(qt)
        images.extend(qi)

    return "\n".join(text_parts), images


class WeComMessageEndpoint(Endpoint):
    def _build_wecom_res(
        self,
        message_id: str,
        content: str,
        finish: bool,
        timestamp: str,
        nonce: str,
        cryptor: WeComCryptor,
    ) -> str:
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

        msgtype = payload.get("msgtype", "")

        # ── Log: WeCom callback raw message ───────────────
        logger.debug(
            f"[WeCom] received msgtype={msgtype} msgid={payload.get('msgid')} "
            f"chattype={payload.get('chattype')} from={payload.get('from', {}).get('userid')} "
            f"payload={json.dumps(payload, ensure_ascii=False)}"
        )

        # Only process supported message types: text / image / mixed / quote
        # stream type is handled separately; other types are silently ignored
        if msgtype not in ("text", "image", "mixed", "quote", "stream"):
            return Response(status=200, response="success")

        # ── Parse message content ──────────────────────────
        query, image_bytes_list = _parse_message(payload, encoding_key)

        # For text/image/mixed types: at least one of query or images must be non-empty
        if msgtype != "stream" and not query and not image_bytes_list:
            return Response(status=200, response="success")

        message_id = payload.get("msgid")
        if self.session.storage.exist(f"wecom_msg_{message_id}"):
            logger.debug(f"Duplicate message detected: {message_id}")
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
            logger.debug(f"Processing new message: {message_id}")
            self.session.storage.set(f"wecom_msg_{message_id}", b"processing")

        if msgtype == "stream":
            stream_id = payload.get("stream", {}).get("id")
            if self.session.storage.exist(f"wecom_msg_{stream_id}"):
                logger.debug(f"Duplicate stream detected: {stream_id}")

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
                logger.debug(f"Processing new stream: {stream_id}")
                self.session.storage.set(f"wecom_msg_{stream_id}", b"processing")

        # ── Upload images to Dify and build the files parameter ──
        # SDK session.file.upload() stores files in the tool_files table (not upload_files)
        # Therefore we must use transfer_method="tool_file" + "tool_file_id" fields
        # to_app_parameter() returns local_file which does not work; build the dict manually
        dify_files: list[dict] = []
        for idx, img_bytes in enumerate(image_bytes_list):
            try:
                upload_resp = self.session.file.upload(
                    filename=f"wecom_image_{idx}.jpg",
                    content=img_bytes,
                    mimetype="image/jpeg",
                )
                dify_files.append(
                    {
                        "transfer_method": "tool_file",
                        "tool_file_id": upload_resp.id,
                        "type": "image",
                    }
                )
                logger.debug(f"[Dify] uploaded image[{idx}] -> tool_file_id={upload_resp.id}")
            except Exception as exc:
                logger.debug(f"[Dify] image upload failed[{idx}]: {exc}")

        # Pure text: inputs={} stays consistent with original logic
        # With images: inputs={"files": [...]} is passed to Dify
        dify_inputs: dict = {}
        if dify_files:
            dify_inputs["files"] = dify_files

        # For pure image messages without text, use a default query so Dify can process it
        effective_query = query if query else "请描述这张图片"

        try:
            app = settings.get("app")
            app_id = app.get("app_id")

            # ── Log: Dify invocation parameters ─────────────
            logger.debug(
                f"[Dify] invoke request: "
                f"app_id={app_id!r} "
                f"query={effective_query!r} "
                f"inputs={json.dumps(dify_inputs, ensure_ascii=False, default=str)} "
                f"files={json.dumps(dify_files, ensure_ascii=False)} "
                f"response_mode='blocking'"
            )

            response = self.session.app.chat.invoke(
                app_id=app_id,
                query=effective_query,
                inputs=dify_inputs,
                response_mode="blocking",
            )
            answer = response.get("answer") or json.dumps(response, ensure_ascii=False)

            # ── Log: Dify response ──────────────────────────
            logger.debug(
                f"[Dify] response app_id={app_id} "
                f"answer_len={len(answer)} "
                f"answer={answer[:200]!r}{'...' if len(answer) > 200 else ''}"
            )
        except Exception as exc:
            logger.debug(f"[Dify] invoke failed: {exc}")
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
