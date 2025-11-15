import base64
import hashlib
import json
import os
import struct
import time
from secrets import token_hex
from typing import Any, Mapping

from Cryptodome.Cipher import AES


class WeComCryptor:
    """Minimal AES-CBC + SHA1 helper for Enterprise WeChat callbacks."""

    def __init__(self, *, token: str, encoding_aes_key: str):
        key = base64.b64decode(encoding_aes_key + "=")
        if len(key) != 32:
            raise ValueError("EncodingAESKey must decode to 32 bytes")
        self.token = token
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

    def encrypt_response(
        self,
        *,
        plain: str,
        timestamp: str | None = None,
        nonce: str | None = None,
    ) -> Mapping[str, Any]:
        if timestamp is None:
            ts_value = int(time.time())
        else:
            try:
                ts_value = int(timestamp)
            except (TypeError, ValueError):
                ts_value = int(time.time())
        if nonce is None:
            nonce = token_hex(8)
        plain_bytes = plain.encode("utf-8")
        msg_len = struct.pack("!I", len(plain_bytes))
        random_bytes = os.urandom(16)
        receive_bytes = "".encode("utf-8")
        data = random_bytes + msg_len + plain_bytes + receive_bytes
        data = self._pkcs7_pad(data)
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        encrypted = base64.b64encode(cipher.encrypt(data)).decode("utf-8")
        signature = self._signature(timestamp=str(ts_value), nonce=nonce, ciphertext=encrypted)
        return {
            "encrypt": encrypted,
            "msgsignature": signature,
            "timestamp": ts_value,
            "nonce": nonce,
        }

    def _signature(self, *, timestamp: str, nonce: str, ciphertext: str) -> str:
        parts = [self.token, str(timestamp), str(nonce), ciphertext]
        parts.sort()
        sha = hashlib.sha1()
        sha.update("".join(parts).encode("utf-8"))
        return sha.hexdigest()

    def _pkcs7_pad(self, data: bytes) -> bytes:
        block_size = 32
        pad_len = block_size - (len(data) % block_size)
        return data + bytes([pad_len]) * pad_len
