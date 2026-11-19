import base64
import binascii
import ipaddress
import re
import socket
import ssl
import time
from collections import OrderedDict
from datetime import datetime
from hashlib import scrypt, sha256
from http.client import HTTPException, HTTPSConnection
from secrets import token_bytes
from threading import Lock
from urllib.parse import urlsplit

from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeServerUnavailableError,
)
from gevent import Timeout

from models._credentials import API_ORIGIN

UPLOAD_PATH = "/upload/v1beta/files"
FILE_PATH = "/v1beta/files/"
HANDLE = re.compile(r"tkf1(?:[0-9a-f]{2}){32,2046}")
UPLOAD_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
CHUNK_BYTES = 8 * 1024 * 1024
MAX_BYTES = 50 * 1024 * 1024
DOWNLOAD_SECONDS = 15
CACHE_TTL = 3600
CACHE_SIZE = 128
_CACHE_SALT = token_bytes(32)
_CACHE: OrderedDict[tuple[str, bytes, str, bytes], tuple[float, str]] = OrderedDict()
_CACHE_LOCK = Lock()


class PublicHTTPSConnection(HTTPSConnection):
    def connect(self) -> None:
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not addresses or any(
            not address.is_global or address.is_multicast
            for address in (ipaddress.ip_address(item[4][0]) for item in addresses)
        ):
            raise InvokeBadRequestError("Gemini attachments must use a public HTTPS address")
        last_error = None
        for family, kind, protocol, _, address in addresses:
            sock = socket.socket(family, kind, protocol)
            try:
                sock.settimeout(self.timeout)
                sock.connect(address)
                sock = self._context.wrap_socket(
                    sock, server_hostname=self.host, do_handshake_on_connect=False
                )
                sock.do_handshake()
                self.sock = sock
                return
            except OSError as error:
                last_error = error
                sock.close()
            except BaseException:
                sock.close()
                raise
        raise OSError("Unable to connect to the attachment host") from last_error


def _download(url: str, max_bytes: int = MAX_BYTES) -> bytes:
    try:
        source = urlsplit(url)
        valid = (
            source.scheme == "https"
            and source.hostname
            and source.username is None
            and source.port in (None, 443)
        )
    except ValueError:
        valid = False
    if not valid:
        raise InvokeBadRequestError("Gemini attachments must use a public HTTPS address")
    transport = PublicHTTPSConnection(
        source.hostname, timeout=DOWNLOAD_SECONDS, context=ssl.create_default_context()
    )
    try:
        target = source.path or "/"
        if source.query:
            target += "?" + source.query
        with Timeout(
            DOWNLOAD_SECONDS, InvokeConnectionError("Gemini attachment download timed out")
        ):
            transport.request("GET", target)
            with transport.getresponse() as response:
                if response.status != 200:
                    raise InvokeBadRequestError("Unable to read Gemini attachment")
                size = response.length
                if size is not None and size > max_bytes:
                    raise InvokeBadRequestError(
                        "Gemini attachment exceeds the remaining size limit"
                    )
                data = response.read(max_bytes + 1)
                if size is not None and len(data) != size:
                    raise InvokeConnectionError("Gemini attachment download ended early")
    except (OSError, HTTPException) as error:
        raise InvokeConnectionError("Unable to read Gemini attachment") from error
    finally:
        transport.close()
    return data


def decode_media(data: str, max_bytes: int) -> bytes:
    if len(data) > ((max_bytes + 2) // 3) * 4:
        raise InvokeBadRequestError("Gemini inline media exceeds the request size limit")
    try:
        decoded = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as error:
        raise InvokeBadRequestError("Gemini attachment must contain valid base64") from error
    if not decoded or len(decoded) > max_bytes:
        raise InvokeBadRequestError("Gemini inline media exceeds the request size limit")
    return decoded


def media_bytes(item, *, max_bytes: int = MAX_BYTES) -> bytes:
    max_bytes = min(max_bytes, MAX_BYTES)
    if max_bytes < 1:
        raise InvokeBadRequestError("Gemini inline media exceeds the request size limit")
    if item.base64_data:
        data = decode_media(item.base64_data, max_bytes)
    elif item.url:
        data = _download(item.url, max_bytes)
    else:
        raise InvokeBadRequestError("Gemini attachment has no data")
    if not data or len(data) > max_bytes:
        raise InvokeBadRequestError("Gemini inline media exceeds the request size limit")
    return data


def _extract_file(response) -> dict:
    payload = response.json()
    if (
        isinstance(payload, dict)
        and (value := payload.get("file", payload))
        and isinstance(value, dict)
    ):
        return value
    raise InvokeServerUnavailableError("Tokener.ai returned an invalid Gemini file")


def _active_file(llm, credentials, file: dict) -> tuple[float, str]:
    uri = file.get("uri", "")
    prefix = API_ORIGIN + FILE_PATH
    if (
        not isinstance(uri, str)
        or not uri.startswith(prefix)
        or not HANDLE.fullmatch(uri[len(prefix) :])
    ):
        raise InvokeServerUnavailableError("Tokener.ai returned an invalid Gemini file handle")
    deadline = time.monotonic() + 30
    while file.get("state") == "PROCESSING":
        if time.monotonic() >= deadline:
            raise InvokeConnectionError("Tokener.ai did not finish processing the Gemini file")
        time.sleep(0.5)
        with llm._request_at(
            uri.removeprefix(API_ORIGIN), credentials, method="GET", timeout=(5, 5)
        ) as response:
            file = _extract_file(response)
    if file.get("state") not in (None, "ACTIVE"):
        raise InvokeServerUnavailableError("Tokener.ai failed to process the Gemini file")
    expiry = time.time() + CACHE_TTL
    if value := file.get("expirationTime"):
        try:
            expiry = min(expiry, datetime.fromisoformat(value).timestamp() - 5)
        except (ValueError, TypeError):
            expiry = time.time()
    return expiry, uri


def upload(llm, credentials: dict, mime: str, data: bytes) -> str:
    cache_key = (
        API_ORIGIN,
        scrypt(credentials["api_key"].encode(), salt=_CACHE_SALT, n=2**14, r=8, p=1, dklen=32),
        mime,
        sha256(data).digest(),
    )
    with _CACHE_LOCK:
        if (cached := _CACHE.get(cache_key)) and cached[0] > time.time():
            _CACHE.move_to_end(cache_key)
            return cached[1]
    headers = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(len(data)),
        "X-Goog-Upload-Header-Content-Type": mime,
    }
    with llm._request_at(
        UPLOAD_PATH,
        credentials,
        headers=headers,
        json={
            "file": {"mime_type": mime, "size_bytes": len(data)},
        },
    ) as response:
        upload_url = response.headers.get("X-Goog-Upload-URL", "")
    prefix = API_ORIGIN + UPLOAD_PATH + "/"
    if not upload_url.startswith(prefix) or not UPLOAD_ID.fullmatch(upload_url[len(prefix) :]):
        raise InvokeServerUnavailableError("Tokener.ai returned an invalid Gemini upload URL")
    upload_path = upload_url.removeprefix(API_ORIGIN)
    for offset in range(0, len(data), CHUNK_BYTES):
        segment = data[offset : offset + CHUNK_BYTES]
        final = offset + len(segment) == len(data)
        with llm._request_at(
            upload_path,
            credentials,
            data=segment,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Goog-Upload-Offset": str(offset),
                "X-Goog-Upload-Command": "upload, finalize" if final else "upload",
            },
        ) as response:
            if final:
                file = _extract_file(response)
    expiry, uri = _active_file(llm, credentials, file)
    with _CACHE_LOCK:
        _CACHE[cache_key] = (expiry, uri)
        _CACHE.move_to_end(cache_key)
        if len(_CACHE) > CACHE_SIZE:
            _CACHE.popitem(last=False)
    return uri
