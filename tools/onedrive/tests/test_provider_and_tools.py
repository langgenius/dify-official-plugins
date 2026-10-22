import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

import provider.onedrive as onedrive_module
from provider.onedrive import OneDriveProvider
from tools import graph_client
from tools.delete_file_by_id import DeleteFileByIdTool
from tools.get_file_by_id import GetFileByIdTool
from tools.search_file import SearchFileTool
from tools.upload_file import UploadFileTool

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SP = {"tenant_id": "contoso.onmicrosoft.com", "client_id": "app-id", "client_secret": "s3cret", "drive_user": "alice@contoso.com"}
OAUTH = {"access_token": "user-token", "refresh_token": "r"}
ITEM = {
    "id": "item1",
    "name": "a.txt",
    "size": 3,
    "@microsoft.graph.downloadUrl": "https://download.example/a",
    "createdDateTime": "2026-10-22T00:00:00Z",
    "lastModifiedDateTime": "2026-10-22T00:00:00Z",
    "parentReference": {"path": "/drive/root:", "driveId": "d1"},
    "webUrl": "https://contoso-my.sharepoint.com/a.txt",
}


class FakeResponse:
    def __init__(self, payload=None, status_code: int = 200, content: bytes | None = None) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = content if content is not None else (b"" if payload is None else json.dumps(payload).encode())
        self.text = self.content.decode(errors="replace")

    def json(self):
        return self._payload


# ── provider ──────────────────────────────────────────────────────────


class FakeMSAL:
    """Stands in for msal.ConfidentialClientApplication, which fetches authority metadata over the network."""

    instances: list["FakeMSAL"] = []
    token_result: dict = {"access_token": "a", "refresh_token": "r2", "expires_in": 3599}

    def __init__(self, client_id, client_credential, authority):
        self.client_id, self.authority, self.scopes = client_id, authority, None
        FakeMSAL.instances.append(self)

    def get_authorization_request_url(self, redirect_uri, scopes, response_type):
        self.scopes = scopes
        return f"{self.authority}/oauth2/v2.0/authorize?scope={' '.join(scopes)}"

    def acquire_token_by_authorization_code(self, code, scopes, redirect_uri):
        self.scopes = scopes
        return dict(FakeMSAL.token_result)

    def acquire_token_by_refresh_token(self, refresh_token, scopes):
        self.scopes = scopes
        return dict(FakeMSAL.token_result)


@pytest.fixture
def msal(monkeypatch):
    FakeMSAL.instances = []
    FakeMSAL.token_result = {"access_token": "a", "refresh_token": "r2", "expires_in": 3599}
    monkeypatch.setattr(onedrive_module, "ConfidentialClientApplication", FakeMSAL)
    return FakeMSAL


def test_authorization_keeps_common_by_default(msal):
    OneDriveProvider()._oauth_get_authorization_url("https://dify.example/cb", {"client_id": "cid", "client_secret": "cs"})
    assert msal.instances[0].authority == "https://login.microsoftonline.com/common"
    assert msal.instances[0].scopes == ["Files.Read.All", "Files.ReadWrite.All"]


def test_authorization_uses_the_configured_tenant(msal):
    # "common" breaks single-tenant app registrations (AADSTS50194), so the tenant must be configurable.
    OneDriveProvider()._oauth_get_authorization_url(
        "https://dify.example/cb", {"client_id": "cid", "client_secret": "cs", "tenant_id": " contoso.onmicrosoft.com "}
    )
    assert msal.instances[0].authority == "https://login.microsoftonline.com/contoso.onmicrosoft.com"


def test_china_authorization_uses_china_login_and_qualified_scopes(msal):
    OneDriveProvider()._oauth_get_authorization_url(
        "https://dify.example/cb", {"client_id": "cid", "client_secret": "cs", "tenant_id": "t.partner.onmschina.cn", "cloud": "china"}
    )
    assert msal.instances[0].authority == "https://login.partner.microsoftonline.cn/t.partner.onmschina.cn"
    assert msal.instances[0].scopes == [
        "https://microsoftgraph.chinacloudapi.cn/Files.Read.All",
        "https://microsoftgraph.chinacloudapi.cn/Files.ReadWrite.All",
    ]


@pytest.mark.parametrize("method", ["_oauth_get_credentials", "_oauth_refresh_credentials"])
def test_oauth_credentials_remember_the_graph_host(msal, method):
    system = {"client_id": "cid", "client_secret": "cs", "tenant_id": "t.onmicrosoft.us", "cloud": "usgov"}
    provider = OneDriveProvider()
    if method == "_oauth_get_credentials":
        result = provider._oauth_get_credentials("https://dify.example/cb", system, SimpleNamespace(args={"code": "c"}))
    else:
        result = provider._oauth_refresh_credentials("https://dify.example/cb", system, {"refresh_token": "r"})
    assert msal.instances[0].authority == "https://login.microsoftonline.us/t.onmicrosoft.us"
    assert result.credentials["graph_base_url"] == "https://graph.microsoft.us"
    assert result.credentials["refresh_token"] == "r2"


def test_msal_error_is_reported_instead_of_key_error(msal):
    msal.token_result = {"error": "invalid_grant", "error_description": "AADSTS70008: The code has expired."}
    with pytest.raises(ToolProviderCredentialValidationError, match="AADSTS70008"):
        OneDriveProvider()._oauth_get_credentials("https://dify.example/cb", {"client_id": "cid", "client_secret": "cs"}, SimpleNamespace(args={"code": "c"}))


def test_refresh_keeps_the_old_refresh_token_when_none_is_returned(msal):
    msal.token_result = {"access_token": "a", "expires_in": 3599}
    result = OneDriveProvider()._oauth_refresh_credentials("https://dify.example/cb", {"client_id": "cid", "client_secret": "cs"}, {"refresh_token": "old"})
    assert result.credentials["refresh_token"] == "old"


def _patch_sp(monkeypatch, status):
    seen = {}
    monkeypatch.setattr(graph_client.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["url"] = url
        return FakeResponse({"id": "drive"}, status)

    monkeypatch.setattr(onedrive_module.requests, "get", fake_get)
    return seen


def test_service_principal_validation_opens_the_default_drive(monkeypatch):
    seen = _patch_sp(monkeypatch, 200)
    OneDriveProvider()._validate_credentials(dict(SP))
    assert seen["url"] == "https://graph.microsoft.com/v1.0/users/alice@contoso.com/drive"


@pytest.mark.parametrize("status, match", [(403, "Files.ReadWrite.All"), (404, "no OneDrive")])
def test_service_principal_validation_errors(monkeypatch, status, match):
    _patch_sp(monkeypatch, status)
    with pytest.raises(ToolProviderCredentialValidationError, match=match):
        OneDriveProvider()._validate_credentials(dict(SP))


def test_provider_yaml():
    data = yaml.safe_load((PLUGIN_ROOT / "provider" / "onedrive.yaml").read_text(encoding="utf-8"))
    assert set(data["credentials_for_provider"]) == {"tenant_id", "client_id", "client_secret", "drive_user", "cloud"}
    client = {f["name"]: f for f in data["oauth_schema"]["client_schema"]}
    assert {"client_id", "client_secret", "tenant_id", "cloud"} <= set(client)
    assert client["tenant_id"]["default"] == "common"
    for field in data["oauth_schema"]["client_schema"]:
        assert "zh_CN" not in field["label"] and "en_US" in field["label"], field["name"]
    for tool in data["tools"]:
        spec = yaml.safe_load((PLUGIN_ROOT / tool).read_text(encoding="utf-8"))
        owner = [p for p in spec["parameters"] if p["name"] == "drive_user"]
        assert len(owner) == 1 and owner[0]["form"] == "form", tool


def test_no_tool_hardcodes_the_global_graph_host_or_uses_the_sdk():
    for path in sorted((PLUGIN_ROOT / "tools").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "msgraph" not in text and "kiota" not in text, path.name
        if path.name != "graph_client.py":
            assert "graph.microsoft.com" not in text, path.name


# ── tools ─────────────────────────────────────────────────────────────


class FakeGraph:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, params=None, data=None, timeout=None):
        self.calls.append(SimpleNamespace(method=method, url=url, headers=headers or {}, params=params, data=data))
        for (m, suffix), response in self.routes.items():
            if m == method and url.endswith(suffix):
                return response
        raise AssertionError(f"unexpected {method} {url}")


def run(cls, params, credentials=OAUTH):
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=credentials)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_blob_message = lambda blob, meta: ("blob", blob, meta)
    return list(tool._invoke(params))


def test_search_quotes_the_query_and_keeps_the_output_shape(monkeypatch):
    fake = FakeGraph({("GET", "/root/search(q='it%27%27s%20a%20test')"): FakeResponse({"value": [ITEM, ITEM]})})
    monkeypatch.setattr(graph_client.requests, "request", fake)
    out = run(SearchFileTool, {"query": "it's a test", "limit": 1})
    # The single quote is doubled for OData, then the whole literal is URL-encoded.
    assert fake.calls[0].url == "https://graph.microsoft.com/v1.0/me/drive/root/search(q='it%27%27s%20a%20test')"
    assert out == [("json", {"results": [graph_client.file_info(ITEM)]})]
    assert out[0][1]["results"][0]["download_url"] == "https://download.example/a"


def test_get_file_downloads_without_the_bearer_token(monkeypatch):
    fake = FakeGraph({("GET", "/items/item1"): FakeResponse(ITEM)})
    monkeypatch.setattr(graph_client.requests, "request", fake)
    downloads = []

    import tools.get_file_by_id as get_module

    def fake_get(url, timeout=None, **kwargs):
        downloads.append((url, kwargs.get("headers")))
        return FakeResponse(None, 200, content=b"abc")

    monkeypatch.setattr(get_module.requests, "get", fake_get)
    out = run(GetFileByIdTool, {"file_id": "item1", "download": True})
    assert downloads == [("https://download.example/a", None)]
    assert out[-1] == ("blob", b"abc", {"file_name": "a.txt"})


def test_upload_puts_content_under_the_service_principal_owner(monkeypatch):
    monkeypatch.setattr(graph_client.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    fake = FakeGraph({("PUT", "/content"): FakeResponse(ITEM, 201)})
    monkeypatch.setattr(graph_client.requests, "request", fake)
    file = SimpleNamespace(blob=b"abc", filename="report 1.txt")
    out = run(UploadFileTool, {"file": file, "file_name": "folder/report 1.txt", "drive_user": "bob@contoso.com"}, dict(SP))
    call = fake.calls[0]
    assert call.url == "https://graph.microsoft.com/v1.0/users/bob@contoso.com/drive/root:/folder/report%201.txt:/content"
    assert call.headers["Authorization"] == "Bearer app"
    assert call.data == b"abc"
    assert out[-1] == ("json", graph_client.file_info(ITEM))


def test_delete_reports_graph_errors(monkeypatch):
    fake = FakeGraph({("DELETE", "/items/missing"): FakeResponse({"error": {"code": "itemNotFound", "message": "Item not found"}}, 404)})
    monkeypatch.setattr(graph_client.requests, "request", fake)
    out = run(DeleteFileByIdTool, {"file_id": "missing"})
    assert out[0][0] == "json" and "OneDrive API error 404: itemNotFound" in out[0][1]["error"]


def test_search_403_with_service_principal_names_sites_read_all(monkeypatch):
    monkeypatch.setattr(graph_client.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    fake = FakeGraph({("GET", "/root/search(q='x')"): FakeResponse({"error": {"code": "accessDenied", "message": "Access denied"}}, 403)})
    monkeypatch.setattr(graph_client.requests, "request", fake)
    out = run(SearchFileTool, {"query": "x"}, dict(SP))
    assert "Sites.Read.All" in out[0][1]
