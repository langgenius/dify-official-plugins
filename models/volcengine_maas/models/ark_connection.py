"""Failure-only diagnostics for the synchronous Ark TCP transport."""

import json
import logging
import socket
from contextvars import ContextVar
from time import monotonic

import httpcore
from dify_plugin import get_current_session
from httpcore._backends.sync import SyncBackend, SyncStream
from httpcore._exceptions import map_exceptions
from volcenginesdkarkruntime import Ark

logger = logging.getLogger(__name__)
_retry_index = ContextVar("ark_retry_index", default=0)


class _ArkNetworkBackend(SyncBackend):
    def __init__(self, via_proxy: bool):
        self.via_proxy = via_proxy

    def _dial(self, host, port, timeout, local_address):
        # Same resolver and address order as socket.create_connection (also under gevent).
        addresses = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
        if not addresses:
            raise OSError("getaddrinfo returns an empty list")

        attempts = []
        try:
            for index, (family, kind, proto, _, address) in enumerate(addresses):
                sock = None
                started = monotonic()
                phase = "socket"
                try:
                    sock = socket.socket(family, kind, proto)
                    sock.settimeout(timeout)
                    if local_address is not None:
                        phase = "bind"
                        sock.bind((local_address, 0))
                    phase = "connect"
                    sock.connect(address)
                except OSError as exc:
                    if sock is not None:
                        sock.close()
                    attempts.append(
                        {
                            "candidate": index,
                            "phase": phase,
                            "error": type(exc).__name__,
                            "errno": exc.errno,
                            "elapsed_ms": round((monotonic() - started) * 1000, 2),
                        }
                    )
                    if index == len(addresses) - 1:
                        raise
                except BaseException:
                    if sock is not None:
                        sock.close()
                    raise
                else:
                    if attempts:
                        attempts.append(
                            {
                                "candidate": index,
                                "phase": "connected",
                                "elapsed_ms": round((monotonic() - started) * 1000, 2),
                            }
                        )
                    return sock
        finally:
            if attempts:
                self._warn(host, port, addresses, attempts)

    def _warn(self, host, port, addresses, attempts):
        try:
            record = {
                "event": "ark_tcp_dial",
                "host": host,
                "port": port,
                "via_proxy": self.via_proxy,
                "retry_index": _retry_index.get(),
                "session_id": getattr(get_current_session(), "session_id", None),
                "candidates": [
                    {"family": socket.AddressFamily(af).name, "ip": addr[0]}
                    for af, _, _, _, addr in addresses
                ],
                "attempts": attempts,
            }
            logger.warning("%s", json.dumps(record))
        except Exception:
            # A failing log sink must not replace the dial result or leak a connected socket.
            pass

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        # Keep HTTPCore's exception mapping and post-connect socket options.
        with map_exceptions({socket.timeout: httpcore.ConnectTimeout, OSError: httpcore.ConnectError}):
            sock = self._dial(host, port, timeout, local_address)
            try:
                for option in socket_options or ():
                    sock.setsockopt(*option)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                return SyncStream(sock)
            except BaseException:
                sock.close()
                raise


class DiagnosticArk(Ark):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if kwargs.get("http_client") is not None:
            return
        # HTTPX has no public backend setter. Keep the SDK-created client, including its
        # proxy mounts, SSL contexts and limits; replace only stock synchronous dialers.
        for transport in (
            getattr(self._client, "_transport", None),
            *getattr(self._client, "_mounts", {}).values(),
        ):
            pool = getattr(transport, "_pool", None)
            if type(getattr(pool, "_network_backend", None)) is SyncBackend:
                pool._network_backend = _ArkNetworkBackend(
                    isinstance(pool, (httpcore.HTTPProxy, httpcore.SOCKSProxy))
                )

    def _retry_request(self, *args, **kwargs):
        # The synchronous SDK calls itself recursively for each retry.
        token = _retry_index.set(_retry_index.get() + 1)
        try:
            return super()._retry_request(*args, **kwargs)
        finally:
            _retry_index.reset(token)
