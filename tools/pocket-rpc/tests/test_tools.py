import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml
from dify_plugin.entities.tool import ToolParameter, ToolRuntime
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from provider.pocket_rpc import PocketRPCProvider
from tools._client import PocketRPCClient, PocketRPCError, CHAINS, NATIVE_SYMBOL
from tools.pocket_block_number import PocketBlockNumberTool
from tools.pocket_balance import PocketBalanceTool
from tools.pocket_transaction import PocketTransactionTool

ETH_URL = "https://eth.api.pocket.network"
CELO_URL = "https://celo.api.pocket.network"

BLOCK_RESULT = "0x1941b91"  # 26483601
CHAIN_ID_RESULT = "0x1"
BALANCE_RESULT = "0x7900812cb295fff48388"

TX_HASH = "0x1b8843678cbaa88d61c8d3a0a556cd2accf79507cd728d832b0259e0dff0c45e"
TX_RESULT = {
    "blockHash": "0x5a05a2ca9b15adadf6a6d99e2599d83a71775e40e04929589b6d94b4a63c97e4",
    "blockNumber": "0x1941b92",
    "from": "0x46565eedb0bb948ae787dd105cce300f736da28e",
    "to": "0x00000000005ad9ce1f5035fd62ca96cef16adaaf",
    "hash": TX_HASH,
    "value": "0x0",
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr("socket.socket.connect", lambda *a, **k: pytest.fail("Unexpected network"))


@pytest.fixture
def transport(monkeypatch):
    calls = []
    handler = SimpleNamespace(callback=None)

    def send(session, request, **kwargs):
        body = json.loads(request.body) if request.body else None
        calls.append((request, body, kwargs))
        status, payload = handler.callback(request, body) if handler.callback else (200, {})
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        response.request = request
        response.headers["Content-Type"] = "application/json"
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    return calls, handler


def rpc_ok(calls, handler):
    def callback(request, body):
        method = body["method"]
        if method == "eth_blockNumber":
            return 200, {"jsonrpc": "2.0", "id": 1, "result": BLOCK_RESULT}
        if method == "eth_chainId":
            return 200, {"jsonrpc": "2.0", "id": 1, "result": CHAIN_ID_RESULT}
        if method == "eth_getBalance":
            return 200, {"jsonrpc": "2.0", "id": 1, "result": BALANCE_RESULT}
        if method == "eth_getTransactionByHash":
            return 200, {"jsonrpc": "2.0", "id": 1, "result": TX_RESULT}
        return 200, {"jsonrpc": "2.0", "id": 1, "result": None}

    handler.callback = callback


def invoke(cls, params, credentials=None):
    creds = {} if credentials is None else credentials
    runtime = ToolRuntime(credentials=creds, user_id=None, session_id=None)
    return list(cls(runtime=runtime, session=None).invoke(params.copy()))


def texts(messages):
    return "\n".join(m.message.text for m in messages if m.type.value == "text")


def test_chains_cover_six_verified_endpoints():
    assert set(CHAINS) == {
        "ethereum", "base", "polygon", "arbitrum-one", "optimism", "celo",
    }
    assert CHAINS["ethereum"] == (ETH_URL, 1)
    assert CHAINS["celo"] == (CELO_URL, 42220)
    assert NATIVE_SYMBOL["celo"] == "CELO"
    assert NATIVE_SYMBOL["polygon"] == "POL"


def test_client_block_number(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    assert PocketRPCClient().block_number("ethereum") == 26483601
    assert calls[0][0].url == ETH_URL + "/"  # requests normalizes the URL
    assert calls[0][1] == {
        "jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": [],
    }


def test_client_chain_id(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    assert PocketRPCClient().chain_id("ethereum") == 1


def test_client_balance(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    balance = PocketRPCClient().balance(
        "ethereum", "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    )
    assert balance == 571415652438114252915592
    assert calls[0][1]["method"] == "eth_getBalance"
    assert calls[0][1]["params"][0] == "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"


def test_client_balance_rejects_bad_address(transport):
    calls, _ = transport
    with pytest.raises(PocketRPCError, match="Invalid address"):
        PocketRPCClient().balance("ethereum", "not-an-address")
    assert not calls


def test_client_transaction(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    tx = PocketRPCClient().transaction("ethereum", TX_HASH)
    assert tx == TX_RESULT
    assert calls[0][1] == {
        "jsonrpc": "2.0", "id": 1,
        "method": "eth_getTransactionByHash", "params": [TX_HASH],
    }


def test_client_transaction_not_found(transport):
    calls, handler = transport
    handler.callback = lambda request, body: (
        200, {"jsonrpc": "2.0", "id": 1, "result": None})
    assert PocketRPCClient().transaction("ethereum", TX_HASH) is None


def test_client_transaction_rejects_bad_hash(transport):
    calls, _ = transport
    with pytest.raises(PocketRPCError, match="Invalid transaction hash"):
        PocketRPCClient().transaction("ethereum", "0x1234")
    assert not calls


def test_client_rejects_unknown_chain(transport):
    calls, _ = transport
    with pytest.raises(PocketRPCError, match="Unsupported chain"):
        PocketRPCClient().block_number("solana")
    assert not calls


def test_client_reports_rpc_error(transport):
    calls, handler = transport
    handler.callback = lambda request, body: (
        200, {"jsonrpc": "2.0", "id": 1,
              "error": {"code": -32601, "message": "the method does not exist"}})
    with pytest.raises(PocketRPCError, match="does not exist"):
        PocketRPCClient().block_number("ethereum")


def test_block_number_tool_returns_json_and_text(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    messages = invoke(PocketBlockNumberTool, {"chain": "ethereum"})
    assert next(m.message.json_object for m in messages if m.type.value == "json") == {
        "chain": "ethereum",
        "chain_id": 1,
        "block_number": 26483601,
        "block_number_hex": "0x1941b91",
    }
    assert "26483601" in texts(messages)


def test_balance_tool_returns_json_and_text(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    messages = invoke(PocketBalanceTool, {
        "chain": "ethereum",
        "address": "0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
    })
    result = next(m.message.json_object for m in messages if m.type.value == "json")
    assert result["balance_wei"] == 571415652438114252915592
    assert result["native_symbol"] == "ETH"
    assert "571415.6524381143" in texts(messages)


def test_balance_tool_requires_address(transport):
    calls, _ = transport
    messages = invoke(PocketBalanceTool, {"chain": "ethereum", "address": ""})
    assert "Please input an address." in texts(messages)
    assert not calls


def test_transaction_tool_returns_json_and_text(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    messages = invoke(PocketTransactionTool, {"chain": "ethereum", "tx_hash": TX_HASH})
    result = next(m.message.json_object for m in messages if m.type.value == "json")
    assert result["transaction"] == TX_RESULT
    assert result["chain_id"] == 1
    assert TX_HASH in texts(messages)
    assert "26483602" in texts(messages)


def test_transaction_tool_not_found(transport):
    calls, handler = transport
    handler.callback = lambda request, body: (
        200, {"jsonrpc": "2.0", "id": 1, "result": None})
    messages = invoke(PocketTransactionTool, {"chain": "ethereum", "tx_hash": TX_HASH})
    assert "No transaction" in texts(messages)


def test_transaction_tool_requires_hash(transport):
    calls, _ = transport
    messages = invoke(PocketTransactionTool, {"chain": "ethereum", "tx_hash": ""})
    assert "Please input a transaction hash." in texts(messages)
    assert not calls


def test_provider_validate_credentials_runs_free_live_check(transport):
    calls, handler = transport
    rpc_ok(calls, handler)
    PocketRPCProvider()._validate_credentials({})
    assert len(calls) == 1
    assert calls[0][1]["method"] == "eth_blockNumber"


def test_provider_validate_credentials_fails_when_endpoint_down(transport):
    calls, handler = transport
    handler.callback = lambda request, body: (
        200, {"jsonrpc": "2.0", "id": 1,
              "error": {"code": -32603, "message": "internal error"}})
    with pytest.raises(ToolProviderCredentialValidationError, match="internal error"):
        PocketRPCProvider()._validate_credentials({})


def test_tool_yaml_schemas_validate():
    base = Path(__file__).resolve().parents[1]
    for name in ("pocket_block_number", "pocket_balance", "pocket_transaction"):
        data = yaml.safe_load((base / "tools" / f"{name}.yaml").read_text())
        params = {p["name"]: ToolParameter.model_validate(p) for p in data["parameters"]}
        assert params
        chain = params["chain"]
        assert chain.type.value == "select"
        assert chain.default == "ethereum"
        assert [o.value for o in chain.options] == [
            "ethereum", "base", "polygon", "arbitrum-one", "optimism", "celo",
        ]
    balance = yaml.safe_load((base / "tools" / "pocket_balance.yaml").read_text())
    params = {p["name"]: ToolParameter.model_validate(p) for p in balance["parameters"]}
    assert params["address"].required is True
