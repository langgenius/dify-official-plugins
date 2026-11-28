import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml
from dify_plugin.entities.tool import ToolRuntime
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR))

from provider.dealport import DealportProvider  # noqa: E402
from tools.find_owner import FindOwnerTool  # noqa: E402
from tools.get_record import GetRecordTool  # noqa: E402
from tools.match_company_list import MatchCompanyListTool  # noqa: E402
from tools.preview_companies import PreviewCompaniesTool  # noqa: E402
from tools.search_buildings import SearchBuildingsTool  # noqa: E402
from tools.search_companies import SearchCompaniesTool  # noqa: E402

TEST_UUID = "123e4567-e89b-12d3-a456-426614174000"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    monkeypatch.setattr("socket.socket.connect", lambda *a, **k: pytest.fail("Unexpected real network call"))


@pytest.fixture
def mock_http(monkeypatch):
    calls = []
    state = SimpleNamespace(status=200, payload={"ok": True})

    def fake_send(session, request, **kwargs):
        body = json.loads(request.body.decode() if isinstance(request.body, bytes) else request.body) if request.body else None
        calls.append((request, body, kwargs))
        resp = requests.Response()
        resp.status_code = state.status
        resp._content = json.dumps(state.payload).encode("utf-8")
        resp.request = request
        resp.headers["Content-Type"] = "application/json"
        return resp

    monkeypatch.setattr(requests.Session, "send", fake_send)
    return calls, state


def run_tool(cls, params, credentials=None):
    creds = {"api_key": "dp_live_secret_test_token"} if credentials is None else credentials
    runtime = ToolRuntime(credentials=creds, user_id=None, session_id=None)
    return list(cls(runtime=runtime, session=None).invoke(dict(params)))


def get_texts(messages):
    return "\n".join(m.message.text for m in messages if m.type.value == "text")


def get_json(messages):
    return next(m.message.json_object for m in messages if m.type.value == "json")


def test_manifest_and_tool_yamls_are_valid():
    manifest = yaml.safe_load((PLUGIN_DIR / "manifest.yaml").read_text())
    assert manifest["author"] == "langgenius"
    assert manifest["name"] == "dealport"
    provider = yaml.safe_load((PLUGIN_DIR / "provider" / "dealport.yaml").read_text())
    assert len(provider["tools"]) == 6
    for rel in provider["tools"]:
        tool_spec = yaml.safe_load((PLUGIN_DIR / rel).read_text())
        source_file = PLUGIN_DIR / tool_spec["extra"]["python"]["source"]
        assert source_file.is_file()


def test_provider_credential_validation(mock_http):
    calls, state = mock_http
    state.payload = {"balance_usd": 5.0}
    provider = DealportProvider()
    provider._validate_credentials({"api_key": "dp_live_valid"})
    assert calls[-1][0].method == "GET"
    assert calls[-1][0].url == "https://app.dealport.com/api/v1/balance"
    assert calls[-1][0].headers["Authorization"] == "Bearer dp_live_valid"

    state.status = 401
    state.payload = {"error": "Invalid key dp_live_secret"}
    with pytest.raises(ToolProviderCredentialValidationError) as exc_info:
        provider._validate_credentials({"api_key": "dp_live_secret"})
    assert "dp_live_secret" not in str(exc_info.value)


def test_preview_companies(mock_http):
    calls, state = mock_http
    state.payload = {
        "total": 412,
        "sample_companies": [{"id": TEST_UUID, "name": "Buckeye Mechanical LLC", "city": "Columbus", "state": "OH"}],
    }
    messages = run_tool(PreviewCompaniesTool, {"state": "oh", "naics": "238220, 332710", "independent": True})
    req, body, _ = calls[-1]
    assert req.method == "POST"
    assert req.url == "https://app.dealport.com/api/v1/companies/preview"
    assert body == {"state": "OH", "naics": ["238220", "332710"], "independent": True}
    assert get_json(messages)["total"] == 412
    assert "412 US companies" in get_texts(messages)


def test_search_companies_and_validation(mock_http):
    calls, state = mock_http
    bad = run_tool(SearchCompaniesTool, {"state": "OHIO"})
    assert not calls
    assert "two-letter US state code" in get_texts(bad)

    state.payload = {"companies": [{"id": TEST_UUID, "name": "Apex Precision Inc", "city": "Dayton", "state": "OH"}]}
    messages = run_tool(SearchCompaniesTool, {"state": "oh", "min_employees": 15, "limit": 10})
    req, _, _ = calls[-1]
    assert req.method == "GET"
    assert "state=OH" in req.url
    assert "min_employees=15" in req.url
    assert "limit=10" in req.url
    assert get_json(messages)["companies"][0]["id"] == TEST_UUID


def test_search_buildings(mock_http):
    calls, state = mock_http
    bad = run_tool(SearchBuildingsTool, {"borough": "NJ"})
    assert not calls
    assert "MN, BK, QN, BX, or SI" in get_texts(bad)

    state.payload = {"buildings": [{"bbl": "1001230045", "address": "120 Broadway", "units": 48}]}
    messages = run_tool(SearchBuildingsTool, {"borough": "mn", "min_units": 20, "loan_holder": "cmbs"})
    req, _, _ = calls[-1]
    assert req.method == "GET"
    assert "borough=MN" in req.url
    assert "loan_holder=cmbs" in req.url
    assert get_json(messages)["buildings"][0]["bbl"] == "1001230045"


def test_get_record_and_path_traversal_guard(mock_http):
    calls, state = mock_http
    bad = run_tool(GetRecordTool, {"record_id": "../balance"})
    assert not calls
    assert "valid Dealport company UUID" in get_texts(bad)

    state.payload = {"id": TEST_UUID, "name": "Midwest Industrial Services"}
    messages = run_tool(GetRecordTool, {"record_id": TEST_UUID})
    assert calls[-1][0].url == f"https://app.dealport.com/api/v1/records/{TEST_UUID}"
    assert "Midwest Industrial Services" in get_texts(messages)


def test_find_owner(mock_http):
    calls, state = mock_http
    bad = run_tool(FindOwnerTool, {"company_id": "not-a-uuid"})
    assert not calls
    assert "valid Dealport company UUID" in get_texts(bad)

    state.payload = {"owner_name": "Jane Founder", "emails": ["jane@example.com"]}
    messages = run_tool(FindOwnerTool, {"company_id": TEST_UUID, "person": "Jane Founder"})
    req, body, _ = calls[-1]
    assert req.method == "POST"
    assert req.url == "https://app.dealport.com/api/v1/owners"
    assert body == {"company_id": TEST_UUID, "person": "Jane Founder"}
    assert "Jane Founder" in get_texts(messages)


def test_match_company_list(mock_http):
    calls, state = mock_http
    empty = run_tool(MatchCompanyListTool, {})
    assert not calls
    assert "provide either csv or items_json" in get_texts(empty)

    state.payload = {"matches": [{"company_id": TEST_UUID, "matched": True}]}
    items = json.dumps([{"name": "Buckeye Mechanical", "domain": "buckeyemech.com", "state": "OH"}])
    messages = run_tool(MatchCompanyListTool, {"items_json": items})
    req, body, _ = calls[-1]
    assert req.method == "POST"
    assert req.url == "https://app.dealport.com/api/v1/companies/match"
    assert body["watch"] is False
    assert len(body["items"]) == 1
    assert "Matched 1 company row(s)" in get_texts(messages)
