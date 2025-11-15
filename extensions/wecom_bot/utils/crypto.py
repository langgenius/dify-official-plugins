from __future__ import annotations

import base64
import hashlib
import json
import struct
from typing import Mapping

from Cryptodome.Cipher import AES


class WeComCryptor:
    """Minimal AES-CBC + SHA1 helper for Enterprise WeChat callbacks."""

    def __init__(self, *, token: str, encoding_aes_key: str, receive_id: str):
        key = base64.b64decode(encoding_aes_key + "=")
        if len(key) != 32:
            raise ValueError("EncodingAESKey must decode to 32 bytes")
        self.token = token
        self.receive_id = receive_id
        self.key = key
        self.iv = key[:16]

    def verify_signature(self, *, signature: str, timestamp: str, nonce: str, ciphertext: str) -> None:
        expected = self._signature(timestamp=timestamp, nonce=nonce, ciphertext=ciphertext)
        if signature != expected:
            raise ValueError("Invalid msg_signature")

    def decrypt(self, *, signature: str, timestamp: str, nonce: str, ciphertext: str) -> Mapping:
        self.verify_signature(signature=signature, timestamp=timestamp, nonce=nonce, ciphertext=ciphertext)
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        decoded = base64.b64decode(ciphertext)
        plain = cipher.decrypt(decoded)
        pad = plain[-1]
        content = plain[16:-pad]
        json_length = struct.unpack("!I", content[:4])[0]
        json_bytes = content[4 : 4 + json_length]
        receive_id = content[4 + json_length :].decode("utf-8", errors="ignore")
        if receive_id != self.receive_id:
            raise ValueError("ReceiveId mismatch")
        return json.loads(json_bytes.decode("utf-8"))

    def decrypt_echostr(self, *, signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        self.verify_signature(signature=signature, timestamp=timestamp, nonce=nonce, ciphertext=echostr)
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        decoded = base64.b64decode(echostr)
        plain = cipher.decrypt(decoded)
        pad = plain[-1]
        content = plain[16:-pad]
        json_length = struct.unpack("!I", content[:4])[0]
        return content[4 : 4 + json_length].decode("utf-8")

    def _signature(self, *, timestamp: str, nonce: str, ciphertext: str) -> str:
        parts = [self.token, str(timestamp), str(nonce), ciphertext]
        parts.sort()
        sha = hashlib.sha1()
        sha.update("".join(parts).encode("utf-8"))
        return sha.hexdigest()
