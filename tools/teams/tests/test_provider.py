from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

import provider.teams as teams_module
from provider.teams import TeamsProvider
from tools.graph_client import CLOUDS

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

# Every delegated scope the tools rely on, restated so that changing _SCOPE is deliberate.
EXPECTED_SCOPES = {
    "User.Read",
    "Team.ReadBasic.All",
    "Channel.ReadBasic.All",
    "ChannelMessage.Send",
    "ChannelMessage.Read.All",
    "Chat.ReadWrite",
    "ChatMessage.Send",
    "Group.Read.All",
    "OnlineMeetings.ReadWrite",
    "Tasks.ReadWrite",
    "offline_access",
}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def test_scopes():
    assert set(TeamsProvider._SCOPE.split()) == EXPECTED_SCOPES


def test_global_authorization_url():
    url = TeamsProvider()._oauth_get_authorization_url("https://dify.example/cb", {"client_id": "cid", "tenant_id": ""})
    parsed = urlparse(url)
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/common/oauth2/v2.0/authorize"
    assert set(parse_qs(parsed.query)["scope"][0].split()) == EXPECTED_SCOPES


def test_china_authorization_url_uses_china_login_and_qualified_scopes():
    url = TeamsProvider()._oauth_get_authorization_url(
        "https://dify.example/cb", {"client_id": "cid", "tenant_id": "t.partner.onmschina.cn", "cloud": "china"}
    )
    parsed = urlparse(url)
    assert parsed.netloc == "login.partner.microsoftonline.cn"
    scopes = parse_qs(parsed.query)["scope"][0].split()
    assert "https://microsoftgraph.chinacloudapi.cn/Tasks.ReadWrite" in scopes
    assert all(s == "offline_access" or s.startswith("https://microsoftgraph.chinacloudapi.cn/") for s in scopes)


@pytest.mark.parametrize("method", ["_oauth_get_credentials", "oauth_refresh_credentials"])
def test_oauth_credentials_remember_the_graph_host(monkeypatch, method):
    posted = {}

    def fake_post(url, data=None, timeout=None):
        posted["url"] = url
        return FakeResponse({"access_token": "a", "refresh_token": "r", "expires_in": 3599})

    monkeypatch.setattr(teams_module.requests, "post", fake_post)
    system = {"client_id": "cid", "client_secret": "cs", "tenant_id": "t.onmicrosoft.us", "cloud": "usgov"}
    provider = TeamsProvider()
    if method == "_oauth_get_credentials":
        result = provider._oauth_get_credentials("https://dify.example/cb", system, SimpleNamespace(args={"code": "c"}))
    else:
        result = provider.oauth_refresh_credentials("https://dify.example/cb", system, {"refresh_token": "r"})
    assert posted["url"] == "https://login.microsoftonline.us/t.onmicrosoft.us/oauth2/v2.0/token"
    assert result.credentials["graph_base_url"] == "https://graph.microsoft.us"


def test_provider_yaml():
    data = yaml.safe_load((PLUGIN_ROOT / "provider" / "teams.yaml").read_text(encoding="utf-8"))
    cloud = next(f for f in data["oauth_schema"]["client_schema"] if f["name"] == "cloud")
    assert {o["value"] for o in cloud["options"]} == set(CLOUDS)
    for tool in data["tools"]:
        spec = yaml.safe_load((PLUGIN_ROOT / tool).read_text(encoding="utf-8"))
        assert (PLUGIN_ROOT / spec["extra"]["python"]["source"]).exists(), tool
        for p in spec.get("parameters") or []:
            assert {"en_US", "zh_Hans", "ja_JP"} <= set(p["label"]), (tool, p["name"])


def test_no_tool_hardcodes_the_global_graph_host():
    for path in sorted((PLUGIN_ROOT / "tools").glob("*.py")):
        if path.name == "graph_client.py":
            continue
        assert "graph.microsoft.com" not in path.read_text(encoding="utf-8"), path.name


PER_USER = {
    "auth_mode": "per_user",
    "tenant_id": "contoso.onmicrosoft.com",
    "client_id": "app-id",
    "client_secret": "s3cret",
    "redirect_uri": "https://dify.example.com/e/hook/teams/callback",
    "cloud": "global",
}


def test_per_user_uses_the_same_scopes_as_oauth():
    from tools.user_auth import DELEGATED_SCOPE

    assert set(DELEGATED_SCOPE.split()) == set(TeamsProvider._SCOPE.split()) == EXPECTED_SCOPES


def test_per_user_validation_checks_the_app_secret(monkeypatch):
    calls = []

    def fake_post(url, data=None, timeout=None):
        calls.append((url, data))
        return FakeResponse({"access_token": "app", "expires_in": 3599})

    monkeypatch.setattr(teams_module.requests, "post", fake_post)
    TeamsProvider()._validate_credentials(dict(PER_USER))
    url, data = calls[0]
    assert url == "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token"
    assert data["grant_type"] == "client_credentials" and data["client_secret"] == "s3cret"


def test_per_user_validation_reports_a_wrong_secret(monkeypatch):
    monkeypatch.setattr(
        teams_module.requests, "post",
        lambda *a, **k: FakeResponse({"error_description": "AADSTS7000215: Invalid client secret provided."}, 401),
    )
    with pytest.raises(teams_module.ToolProviderCredentialValidationError, match="AADSTS7000215"):
        TeamsProvider()._validate_credentials(dict(PER_USER))


def test_per_user_validation_skips_the_secret_check_for_multi_tenant_apps(monkeypatch):
    monkeypatch.setattr(teams_module.requests, "post", lambda *a, **k: pytest.fail("no token request expected"))
    TeamsProvider()._validate_credentials(dict(PER_USER, tenant_id="organizations"))


@pytest.mark.parametrize(
    "redirect_uri, message",
    [
        ("", "Callback URL"),
        ("dify.example.com/teams/callback", "Callback URL"),
        ("https://dify.example.com/e/hook/outlook/callback", "/teams/callback"),
        ("http://localhost/e/hook/teams/callback", "localhost"),
        ("http://127.0.0.1/e/hook/teams/callback", "localhost"),
    ],
)
def test_per_user_validation_checks_the_callback_url(redirect_uri, message):
    with pytest.raises(teams_module.ToolProviderCredentialValidationError, match=message):
        TeamsProvider()._validate_credentials(dict(PER_USER, redirect_uri=redirect_uri))


def test_provider_yaml_has_the_per_user_form_and_sign_out():
    spec = yaml.safe_load((PLUGIN_ROOT / "provider" / "teams.yaml").read_text(encoding="utf-8"))
    form = spec["credentials_for_provider"]
    assert set(form) == {"auth_mode", "tenant_id", "client_id", "client_secret", "redirect_uri", "cloud"}
    assert form["client_secret"]["type"] == "secret-input"
    assert "tools/teams_sign_out.yaml" in spec["tools"]
    manifest = yaml.safe_load((PLUGIN_ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["plugins"]["endpoints"] == ["group/teams_signin.yaml"]
    assert manifest["resource"]["permission"]["storage"]["enabled"]
    endpoint = yaml.safe_load((PLUGIN_ROOT / "endpoints" / "signin_callback.yaml").read_text(encoding="utf-8"))
    assert endpoint["path"] == "/teams/callback"
