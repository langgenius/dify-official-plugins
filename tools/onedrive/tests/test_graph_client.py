from types import SimpleNamespace

import pytest

from tools import graph_client
from tools.graph_client import GraphAuthError, acquire_app_token, resolve_graph_context, setting_value

SP = {
    "tenant_id": "contoso.onmicrosoft.com",
    "client_id": "app-id",
    "client_secret": "s3cret",
    "drive_user": "alice@contoso.com",
}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def token_calls(monkeypatch):
    calls = []

    def fake_post(url, data=None, timeout=None):
        calls.append(SimpleNamespace(url=url, data=data))
        return FakeResponse({"access_token": f"app-token-{len(calls)}", "expires_in": 3599})

    monkeypatch.setattr(graph_client.requests, "post", fake_post)
    return calls


def test_oauth_uses_my_drive_on_global_graph():
    ctx = resolve_graph_context({"access_token": "user-token", "refresh_token": "r"})
    assert ctx.drive_base == "https://graph.microsoft.com/v1.0/me/drive"


def test_oauth_follows_the_stored_national_cloud():
    ctx = resolve_graph_context({"access_token": "t", "graph_base_url": "https://microsoftgraph.chinacloudapi.cn"})
    assert ctx.drive_base == "https://microsoftgraph.chinacloudapi.cn/v1.0/me/drive"


def test_oauth_token_is_never_sent_to_an_unknown_host():
    with pytest.raises(GraphAuthError, match="Unsupported"):
        resolve_graph_context({"access_token": "t", "graph_base_url": "https://evil.example"})


def test_oauth_rejects_the_drive_owner_parameter():
    with pytest.raises(GraphAuthError, match="Service Principal"):
        resolve_graph_context({"access_token": "t"}, drive_user="bob@contoso.com")


def test_service_principal_uses_client_credentials_and_the_default_owner(token_calls):
    ctx = resolve_graph_context(SP)
    call = token_calls[0]
    assert call.url == "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token"
    assert call.data["grant_type"] == "client_credentials"
    assert call.data["scope"] == "https://graph.microsoft.com/.default"
    assert ctx.drive_base == "https://graph.microsoft.com/v1.0/users/alice@contoso.com/drive"


def test_drive_owner_parameter_overrides_the_default(token_calls):
    ctx = resolve_graph_context(SP, drive_user="bob@contoso.com")
    assert ctx.drive_base.endswith("/users/bob@contoso.com/drive")


def test_drive_owner_is_url_encoded(token_calls):
    ctx = resolve_graph_context(SP, drive_user="a/b?c@contoso.com")
    assert ctx.drive_base.endswith("/users/a%2Fb%3Fc@contoso.com/drive")


@pytest.mark.parametrize(
    "raw",
    [
        "{'value': 'bob@contoso.com', 'type': <ToolInputType.CONSTANT: 'constant'>}",
        {"type": "constant", "value": "bob@contoso.com"},
        "  bob@contoso.com ",
    ],
)
def test_drive_owner_setting_is_unwrapped(token_calls, raw):
    # Dify 1.16.1 passes form settings as the repr of the editor's {"type", "value"} wrapper.
    assert resolve_graph_context(SP, drive_user=raw).drive_base.endswith("/users/bob@contoso.com/drive")


def test_unwrapping_does_not_evaluate_anything_else():
    raw = "{'value': __import__('os'), 'type': <ToolInputType.CONSTANT: 'constant'>}"
    assert setting_value(raw) == raw


def test_service_principal_needs_a_drive_owner(token_calls):
    with pytest.raises(GraphAuthError, match="no signed-in user"):
        resolve_graph_context(dict(SP, drive_user=""))


def test_app_token_is_cached(token_calls):
    resolve_graph_context(SP)
    resolve_graph_context(SP, drive_user="bob@contoso.com")
    assert len(token_calls) == 1


@pytest.mark.parametrize(
    "cloud, login, graph",
    [
        ("china", "https://login.partner.microsoftonline.cn", "https://microsoftgraph.chinacloudapi.cn"),
        ("usgov", "https://login.microsoftonline.us", "https://graph.microsoft.us"),
        ("dod", "https://login.microsoftonline.us", "https://dod-graph.microsoft.us"),
    ],
)
def test_national_clouds_switch_login_scope_and_graph_together(token_calls, cloud, login, graph):
    ctx = resolve_graph_context(dict(SP, cloud=cloud))
    assert token_calls[0].url.startswith(f"{login}/")
    assert token_calls[0].data["scope"] == f"{graph}/.default"
    assert ctx.drive_base.startswith(f"{graph}/v1.0/users/")


@pytest.mark.parametrize("tenant", ["common", "organizations", "Consumers"])
def test_multi_tenant_aliases_are_rejected(token_calls, tenant):
    with pytest.raises(GraphAuthError, match="own Tenant ID"):
        acquire_app_token(tenant, "app-id", "s3cret")
    assert token_calls == []


def test_sign_in_failure_surfaces_the_entra_error(monkeypatch):
    monkeypatch.setattr(
        graph_client.requests,
        "post",
        lambda *a, **k: FakeResponse({"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret."}, 401),
    )
    with pytest.raises(GraphAuthError, match="AADSTS7000215"):
        acquire_app_token("contoso.onmicrosoft.com", "app-id", "wrong")
