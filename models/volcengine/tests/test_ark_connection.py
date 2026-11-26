import errno
import json
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import httpcore
import httpx
import pytest
from dify_plugin.core.session_context import use_current_session
from volcenginesdkarkruntime._exceptions import ArkAPIConnectionError

from models.ark_connection import DiagnosticArk, _ArkNetworkBackend

IPV4 = (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.1", 443))
IPV6 = (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("2001:db8::1", 443, 0, 0))


def dial_results(monkeypatch, outcomes):
    sockets = []
    outcomes = iter(outcomes)

    def make_socket(*args):
        sock = Mock()
        sock.connect.side_effect = next(outcomes)
        sockets.append(sock)
        return sock

    monkeypatch.setattr(socket, "getaddrinfo", lambda *args: [IPV4, IPV6])
    monkeypatch.setattr(socket, "socket", make_socket)
    return sockets


def warnings(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "models.ark_connection"]


def test_both_failures_preserved_across_sdk_retry(monkeypatch, caplog):
    monkeypatch.setenv("NO_PROXY", "*")
    with DiagnosticArk(
        base_url="https://example.test/private", api_key="secret-value", max_retries=1
    ) as client:
        monkeypatch.setattr(client, "_calculate_retry_timeout", lambda *args: 0)
        sockets = dial_results(
            monkeypatch,
            [
                TimeoutError(errno.ETIMEDOUT, "IPv4"),
                OSError(errno.EADDRNOTAVAIL, "IPv6"),
                TimeoutError(errno.ETIMEDOUT, "IPv4"),
                OSError(errno.EADDRNOTAVAIL, "IPv6"),
            ],
        )
        with (
            use_current_session(SimpleNamespace(session_id="test-session")),
            pytest.raises(ArkAPIConnectionError) as exc,
        ):
            client.chat.completions.create(
                model="test", messages=[{"role": "user", "content": "private-prompt"}]
            )

    assert isinstance(exc.value.__cause__, httpx.ConnectError)
    assert str(exc.value.__cause__) == str(OSError(errno.EADDRNOTAVAIL, "IPv6"))
    records = warnings(caplog)
    assert [r["retry_index"] for r in records] == [0, 1]
    for record in records:
        assert record["session_id"] == "test-session"
        assert record["candidates"] == [
            {"family": "AF_INET", "ip": IPV4[4][0]},
            {"family": "AF_INET6", "ip": IPV6[4][0]},
        ]
        assert [a["errno"] for a in record["attempts"]] == [errno.ETIMEDOUT, errno.EADDRNOTAVAIL]
        assert [a["candidate"] for a in record["attempts"]] == [0, 1]
        assert all(a["elapsed_ms"] >= 0 for a in record["attempts"])
    for sock in sockets:
        sock.close.assert_called_once()
    assert all(value not in str(records) for value in ("private-prompt", "secret-value", "/private"))


@pytest.mark.parametrize("fallback", [False, True])
def test_successful_dial(monkeypatch, caplog, fallback):
    sockets = dial_results(
        monkeypatch, [OSError(errno.ENETUNREACH, "unreachable"), None] if fallback else [None]
    )
    option = (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    stream = _ArkNetworkBackend(False).connect_tcp("example.test", 443, 7, "127.0.0.1", [option])
    connected = sockets[-1]
    connected.settimeout.assert_called_once_with(7)
    connected.bind.assert_called_once_with(("127.0.0.1", 0))
    connected.connect.assert_called_once_with((IPV6 if fallback else IPV4)[4])
    connected.setsockopt.assert_any_call(*option)
    connected.setsockopt.assert_any_call(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    stream.close()
    records = warnings(caplog)
    if fallback:
        assert len(records) == 1
        assert [a["phase"] for a in records[0]["attempts"]] == ["connect", "connected"]
        assert records[0]["attempts"][0]["errno"] == errno.ENETUNREACH
        sockets[0].close.assert_called_once()
    else:
        assert records == []


def test_preserves_proxy_and_custom_transport(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://user:private@example.test:8080")
    monkeypatch.setenv("NO_PROXY", "direct.test")
    with DiagnosticArk(api_key="unused") as client:
        direct = client._client._transport_for_url(httpx.URL("https://direct.test"))
        proxy = client._client._transport_for_url(httpx.URL("https://proxy-target.test"))
        assert type(direct._pool) is httpcore.ConnectionPool
        assert not direct._pool._network_backend.via_proxy
        assert isinstance(proxy._pool, httpcore.HTTPProxy)
        assert proxy._pool._network_backend.via_proxy

    transport = httpx.MockTransport(lambda request: httpx.Response(204))
    supplied = httpx.Client(transport=transport)
    with DiagnosticArk(api_key="unused", http_client=supplied) as client:
        assert client._client is supplied
        assert supplied.get("https://direct.test").status_code == 204


def test_log_sink_failure_does_not_break_fallback(monkeypatch):
    sockets = dial_results(monkeypatch, [OSError(errno.ENETUNREACH, "unreachable"), None])
    monkeypatch.setattr(
        "models.ark_connection.logger.warning", Mock(side_effect=RuntimeError("sink unavailable"))
    )
    _ArkNetworkBackend(False).connect_tcp("example.test", 443).close()
    assert all(sock.close.call_count == 1 for sock in sockets)
