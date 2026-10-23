from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import yaml
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

import provider.outlook as outlook_module
from provider.outlook import OutlookProvider
from tools import graph_client

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SP = {
    "tenant_id": "contoso.onmicrosoft.com",
    "client_id": "app-id",
    "client_secret": "s3cret",
    "mailbox": "support@contoso.com",
}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def test_global_authorization_url_is_unchanged():
    url = OutlookProvider()._oauth_get_authorization_url(
        "https://dify.example/cb", {"client_id": "cid", "tenant_id": "contoso.onmicrosoft.com"}
    )
    parsed = urlparse(url)
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/contoso.onmicrosoft.com/oauth2/v2.0/authorize"
    assert parse_qs(parsed.query)["scope"] == [OutlookProvider._SCOPE]


def test_blank_tenant_falls_back_to_common():
    url = OutlookProvider()._oauth_get_authorization_url("https://dify.example/cb", {"client_id": "cid", "tenant_id": ""})
    assert urlparse(url).path == "/common/oauth2/v2.0/authorize"


def test_china_authorization_url_uses_china_login_and_qualified_scopes():
    url = OutlookProvider()._oauth_get_authorization_url(
        "https://dify.example/cb", {"client_id": "cid", "tenant_id": "contoso.partner.onmschina.cn", "cloud": "china"}
    )
    parsed = urlparse(url)
    assert parsed.netloc == "login.partner.microsoftonline.cn"
    scopes = parse_qs(parsed.query)["scope"][0].split()
    assert "offline_access" in scopes
    assert "https://microsoftgraph.chinacloudapi.cn/Mail.Send" in scopes
    assert all(s == "offline_access" or s.startswith("https://microsoftgraph.chinacloudapi.cn/") for s in scopes)


@pytest.mark.parametrize("method", ["_oauth_get_credentials", "oauth_refresh_credentials"])
def test_oauth_credentials_remember_the_graph_host(monkeypatch, method):
    posted = {}

    def fake_post(url, data=None, timeout=None):
        posted["url"] = url
        return FakeResponse({"access_token": "a", "refresh_token": "r", "expires_in": 3599})

    monkeypatch.setattr(outlook_module.requests, "post", fake_post)
    system = {"client_id": "cid", "client_secret": "cs", "tenant_id": "t.onmicrosoft.us", "cloud": "usgov"}
    provider = OutlookProvider()
    if method == "_oauth_get_credentials":
        result = provider._oauth_get_credentials("https://dify.example/cb", system, SimpleNamespace(args={"code": "c"}))
    else:
        result = provider.oauth_refresh_credentials("https://dify.example/cb", system, {"refresh_token": "r"})

    assert posted["url"] == "https://login.microsoftonline.us/t.onmicrosoft.us/oauth2/v2.0/token"
    assert result.credentials["graph_base_url"] == "https://graph.microsoft.us"


def _patch_sp(monkeypatch, get_status: int):
    seen = {}
    monkeypatch.setattr(
        graph_client.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599})
    )

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["url"] = url
        seen["auth"] = headers["Authorization"]
        return FakeResponse({"id": "inbox"}, get_status)

    monkeypatch.setattr(outlook_module.requests, "get", fake_get)
    return seen


def test_service_principal_validation_reads_the_default_mailbox(monkeypatch):
    seen = _patch_sp(monkeypatch, 200)
    OutlookProvider()._validate_credentials(dict(SP))
    assert seen["url"] == "https://graph.microsoft.com/v1.0/users/support@contoso.com/mailFolders/inbox"
    assert seen["auth"] == "Bearer app"


def test_service_principal_without_permissions_gets_a_clear_error(monkeypatch):
    _patch_sp(monkeypatch, 403)
    with pytest.raises(ToolProviderCredentialValidationError, match="admin consent"):
        OutlookProvider()._validate_credentials(dict(SP))


def test_service_principal_unknown_mailbox(monkeypatch):
    _patch_sp(monkeypatch, 404)
    with pytest.raises(ToolProviderCredentialValidationError, match="not found"):
        OutlookProvider()._validate_credentials(dict(SP))


def test_service_principal_bad_tenant_is_a_validation_error():
    with pytest.raises(ToolProviderCredentialValidationError, match="own Tenant ID"):
        OutlookProvider()._validate_credentials(dict(SP, tenant_id="common"))


def test_provider_yaml_offers_both_credential_types():
    data = yaml.safe_load((PLUGIN_ROOT / "provider" / "outlook.yaml").read_text(encoding="utf-8"))
    assert set(data["credentials_for_provider"]) == {"tenant_id", "client_id", "client_secret", "mailbox", "cloud"}
    client_fields = {f["name"] for f in data["oauth_schema"]["client_schema"]}
    assert {"client_id", "client_secret", "tenant_id", "cloud"} <= client_fields

    cloud_options = {o["value"] for o in data["credentials_for_provider"]["cloud"]["options"]}
    assert cloud_options == set(graph_client.CLOUDS)
    oauth_cloud = next(f for f in data["oauth_schema"]["client_schema"] if f["name"] == "cloud")
    assert {o["value"] for o in oauth_cloud["options"]} == set(graph_client.CLOUDS)


def test_every_tool_has_a_form_only_mailbox_parameter():
    for path in sorted((PLUGIN_ROOT / "tools").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        mailbox = [p for p in data["parameters"] if p["name"] == "mailbox"]
        assert len(mailbox) == 1, path.name
        # The LLM must not pick which mailbox an app-only token reads.
        assert mailbox[0]["form"] == "form", path.name
        assert mailbox[0]["required"] is False, path.name


def test_no_tool_hardcodes_the_global_graph_host():
    for path in sorted((PLUGIN_ROOT / "tools").glob("*.py")):
        if path.name == "graph_client.py":
            continue
        assert "graph.microsoft.com" not in path.read_text(encoding="utf-8"), path.name
