from types import SimpleNamespace

import pytest

from tools import graph_client
from tools.graph_client import GraphAuthError, acquire_app_token, resolve_graph_context

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


@pytest.fixture
def token_calls(monkeypatch):
    calls = []

    def fake_post(url, data=None, timeout=None):
        calls.append(SimpleNamespace(url=url, data=data))
        return FakeResponse({"access_token": f"app-token-{len(calls)}", "expires_in": 3599})

    monkeypatch.setattr(graph_client.requests, "post", fake_post)
    return calls


def test_oauth_credentials_target_me_on_global_graph():
    ctx = resolve_graph_context({"access_token": "user-token", "refresh_token": "r"})
    assert ctx.access_token == "user-token"
    assert ctx.mailbox_base == "https://graph.microsoft.com/v1.0/me"


def test_oauth_credentials_follow_the_stored_national_cloud():
    ctx = resolve_graph_context(
        {"access_token": "t", "graph_base_url": "https://microsoftgraph.chinacloudapi.cn"}
    )
    assert ctx.mailbox_base == "https://microsoftgraph.chinacloudapi.cn/v1.0/me"


def test_oauth_token_is_never_sent_to_an_unknown_host():
    with pytest.raises(GraphAuthError, match="Unsupported"):
        resolve_graph_context({"access_token": "t", "graph_base_url": "https://evil.example"})


def test_oauth_rejects_the_mailbox_parameter():
    with pytest.raises(GraphAuthError, match="Service Principal"):
        resolve_graph_context({"access_token": "t"}, mailbox="someone@contoso.com")


def test_service_principal_uses_client_credentials_and_the_default_mailbox(token_calls):
    ctx = resolve_graph_context(SP)

    assert len(token_calls) == 1
    call = token_calls[0]
    assert call.url == "https://login.microsoftonline.com/contoso.onmicrosoft.com/oauth2/v2.0/token"
    assert call.data["grant_type"] == "client_credentials"
    assert call.data["scope"] == "https://graph.microsoft.com/.default"
    assert ctx.access_token == "app-token-1"
    assert ctx.mailbox_base == "https://graph.microsoft.com/v1.0/users/support@contoso.com"


def test_tool_mailbox_parameter_overrides_the_default(token_calls):
    ctx = resolve_graph_context(SP, mailbox="sales@contoso.com")
    assert ctx.mailbox_base.endswith("/users/sales@contoso.com")


def test_mailbox_is_url_encoded(token_calls):
    ctx = resolve_graph_context(SP, mailbox="a/b?c@contoso.com")
    assert ctx.mailbox_base.endswith("/users/a%2Fb%3Fc@contoso.com")


@pytest.mark.parametrize(
    "raw",
    [
        "{'value': 'sales@contoso.com', 'type': <ToolInputType.CONSTANT: 'constant'>}",
        "{'value': 'sales@contoso.com', 'type': <ToolInputType.MIXED: 'mixed'>}",
        {"type": "constant", "value": "sales@contoso.com"},
        "  sales@contoso.com  ",
    ],
)
def test_mailbox_setting_is_unwrapped(token_calls, raw):
    # Dify 1.16.1 passes form settings as the repr of the editor's {"type", "value"} wrapper.
    ctx = resolve_graph_context(SP, mailbox=raw)
    assert ctx.mailbox_base.endswith("/users/sales@contoso.com")


def test_unwrapping_does_not_evaluate_anything_else():
    assert graph_client.setting_value("{'value': __import__('os'), 'type': <ToolInputType.CONSTANT: 'constant'>}") == (
        "{'value': __import__('os'), 'type': <ToolInputType.CONSTANT: 'constant'>}"
    )
    assert graph_client.setting_value(None) == ""
    assert graph_client.setting_value({"type": "constant", "value": None}) == ""


def test_service_principal_needs_a_mailbox(token_calls):
    creds = dict(SP, mailbox="")
    with pytest.raises(GraphAuthError, match="no signed-in user"):
        resolve_graph_context(creds)


def test_app_token_is_cached(token_calls):
    resolve_graph_context(SP)
    resolve_graph_context(SP, mailbox="other@contoso.com")
    assert len(token_calls) == 1


def test_changing_the_secret_does_not_reuse_the_cached_token(token_calls):
    resolve_graph_context(SP)
    resolve_graph_context(dict(SP, client_secret="rotated"))
    assert len(token_calls) == 2


def test_expired_token_is_fetched_again(token_calls, monkeypatch):
    resolve_graph_context(SP)
    real_time = graph_client.time.time
    monkeypatch.setattr(graph_client.time, "time", lambda: real_time() + 3600)
    resolve_graph_context(SP)
    assert len(token_calls) == 2


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
    assert ctx.mailbox_base.startswith(f"{graph}/v1.0/users/")


def test_unknown_cloud_is_rejected(token_calls):
    with pytest.raises(GraphAuthError, match="Unknown Microsoft cloud"):
        resolve_graph_context(dict(SP, cloud="mars"))
    assert token_calls == []


@pytest.mark.parametrize("tenant", ["common", "organizations", "Consumers"])
def test_multi_tenant_aliases_are_rejected(token_calls, tenant):
    with pytest.raises(GraphAuthError, match="own Tenant ID"):
        acquire_app_token(tenant, "app-id", "s3cret")
    assert token_calls == []


def test_tenant_cannot_reshape_the_token_url(token_calls):
    with pytest.raises(GraphAuthError, match="GUID or a domain"):
        acquire_app_token("contoso/../evil", "app-id", "s3cret")


def test_sign_in_failure_surfaces_the_entra_error(monkeypatch):
    monkeypatch.setattr(
        graph_client.requests,
        "post",
        lambda *a, **k: FakeResponse(
            {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret."}, 401
        ),
    )
    with pytest.raises(GraphAuthError, match="AADSTS7000215"):
        acquire_app_token("contoso.onmicrosoft.com", "app-id", "wrong")
