import errno
import json
import socket
from unittest.mock import Mock

import pytest
from volcenginesdkarkruntime._exceptions import ArkAPIConnectionError

from models.client import ArkClientV3


def test_embedding_dial_logs_earlier_failure(monkeypatch, caplog):
    monkeypatch.setenv("NO_PROXY", "*")
    client = ArkClientV3(api_key="unused", max_retries=0)
    with client.ark:
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda *args: [
                (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.0.2.1", 443)),
                (socket.AF_INET6, socket.SOCK_STREAM, 0, "", ("2001:db8::1", 443, 0, 0)),
            ],
        )
        sockets = [Mock(), Mock()]
        sockets[0].connect.side_effect = TimeoutError(errno.ETIMEDOUT, "timeout")
        sockets[1].connect.side_effect = OSError(errno.EADDRNOTAVAIL, "unavailable")
        monkeypatch.setattr(socket, "socket", Mock(side_effect=sockets))
        client.endpoint_id = "test-model"
        with pytest.raises(ArkAPIConnectionError):
            client.embeddings(["test input"])

    records = [json.loads(r.getMessage()) for r in caplog.records if r.name == "models.ark_connection"]
    assert len(records) == 1
    assert records[0]["retry_index"] == 0
    assert [a["errno"] for a in records[0]["attempts"]] == [errno.ETIMEDOUT, errno.EADDRNOTAVAIL]
    assert all(sock.close.call_count == 1 for sock in sockets)
