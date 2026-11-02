import json
import time
import urllib.parse
from types import SimpleNamespace

import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from endpoints.signin_callback import SignInCallbackEndpoint
from tools import user_auth
from tools.graph_client import GraphAuthError, is_per_user, is_service_principal, resolve_graph_context, user_sign_in

PER_USER = {
    "auth_mode": "per_user",
    "tenant_id": "contoso.onmicrosoft.com",
    "client_id": "app-id",
    "client_secret": "s3cret",
    "redirect_uri": "https://dify.example.com/e/hook/outlook/callback",
}


class FakeStorage:
    def __init__(self):
        self.data: dict[str, bytes] = {}

    def set(self, key, val):
        self.data[key] = val

    def get(self, key):
        return self.data[key]

    def exist(self, key):
        return key in self.data

    def delete(self, key):
        self.data.pop(key, None)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def make_tool(storage, user_id="user-1", credentials=PER_USER):
    return SimpleNamespace(
        runtime=SimpleNamespace(credentials=credentials, user_id=user_id),
        session=SimpleNamespace(storage=storage),
    )


@pytest.fixture
def token_endpoint(monkeypatch):
    calls = []
    responses = []

    def fake_post(url, data=None, timeout=None):
        calls.append(SimpleNamespace(url=url, data=data))
        if responses:
            return responses.pop(0)
        n = len(calls)
        return FakeResponse({"access_token": f"access-{n}", "refresh_token": f"refresh-{n}", "expires_in": 3599})

    monkeypatch.setattr(user_auth.requests, "post", fake_post)
    # The /me lookup after sign-in; tests that care about the account name override it.
    monkeypatch.setattr(user_auth.requests, "get", lambda url, **kw: FakeResponse({}, 404))
    return SimpleNamespace(calls=calls, responses=responses)


def sign_in_link(storage, tool) -> str:
    with pytest.raises(GraphAuthError) as exc:
        resolve_graph_context(PER_USER, tool=tool)
    return exc.value.args[0].rsplit("\n", 1)[-1]


def call_callback(storage, query: dict):
    request = Request(EnvironBuilder(path="/outlook/callback", query_string=query).get_environ())
    return SignInCallbackEndpoint(SimpleNamespace(storage=storage)).invoke(request, {}, {})


def test_per_user_is_not_mistaken_for_a_service_principal():
    assert is_per_user(PER_USER)
    assert not is_service_principal(PER_USER)
    legacy_sp = {k: v for k, v in PER_USER.items() if k not in ("auth_mode", "redirect_uri")}
    assert is_service_principal(legacy_sp) and not is_per_user(legacy_sp)


def test_first_call_returns_a_pkce_sign_in_link(token_endpoint):
    storage = FakeStorage()
    link = sign_in_link(storage, make_tool(storage))

    parsed = urllib.parse.urlparse(link)
    query = urllib.parse.parse_qs(parsed.query)
    assert parsed.netloc == "login.microsoftonline.com"
    assert parsed.path == "/contoso.onmicrosoft.com/oauth2/v2.0/authorize"
    assert query["redirect_uri"] == [PER_USER["redirect_uri"]]
    assert query["code_challenge_method"] == ["S256"]
    assert "Calendars.ReadWrite" in query["scope"][0]
    assert storage.exist(user_auth.signin_key(query["state"][0]))
    assert token_endpoint.calls == []


def test_full_sign_in_then_cached_then_refreshed(token_endpoint):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(sign_in_link(storage, tool)).query)["state"][0]

    # Asking again before the callback repeats the link instead of starting over.
    with pytest.raises(GraphAuthError, match="not been completed"):
        resolve_graph_context(PER_USER, tool=tool)

    response = call_callback(storage, {"state": state, "code": "auth-code"})
    assert response.status_code == 200

    ctx = resolve_graph_context(PER_USER, tool=tool)
    assert ctx.access_token == "access-1"
    assert ctx.mailbox_base == "https://graph.microsoft.com/v1.0/me"
    exchange = token_endpoint.calls[0].data
    assert exchange["grant_type"] == "authorization_code"
    assert exchange["code"] == "auth-code"
    assert exchange["client_secret"] == "s3cret"
    assert exchange["code_verifier"]
    # The one-time state and code are gone.
    assert not any(key.startswith("signin/") for key in storage.data)

    assert resolve_graph_context(PER_USER, tool=tool).access_token == "access-1"
    assert len(token_endpoint.calls) == 1

    store = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    token = store.load("token")
    token["expires_at"] = time.time()
    store.save("token", token)
    assert resolve_graph_context(PER_USER, tool=tool).access_token == "access-2"
    assert token_endpoint.calls[1].data["grant_type"] == "refresh_token"
    assert token_endpoint.calls[1].data["refresh_token"] == "refresh-1"


def test_tokens_are_per_user_and_encrypted(token_endpoint):
    storage = FakeStorage()
    alice, bob = make_tool(storage, "alice"), make_tool(storage, "bob")
    state = urllib.parse.parse_qs(urllib.parse.urlparse(sign_in_link(storage, alice)).query)["state"][0]
    call_callback(storage, {"state": state, "code": "alice-code"})
    assert resolve_graph_context(PER_USER, tool=alice).access_token == "access-1"

    with pytest.raises(GraphAuthError, match="has not signed in"):
        resolve_graph_context(PER_USER, tool=bob)
    assert not any(b"access-1" in value or b"refresh-1" in value for value in storage.data.values())


def test_rotating_the_client_secret_signs_users_out(token_endpoint):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(sign_in_link(storage, tool)).query)["state"][0]
    call_callback(storage, {"state": state, "code": "c"})
    resolve_graph_context(PER_USER, tool=tool)

    rotated = dict(PER_USER, client_secret="new-secret")
    with pytest.raises(GraphAuthError, match="has not signed in"):
        resolve_graph_context(rotated, tool=make_tool(storage, credentials=rotated))


def test_revoked_refresh_token_asks_to_sign_in_again(token_endpoint):
    storage = FakeStorage()
    store = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    store.save("token", {"access_token": "old", "refresh_token": "revoked", "expires_at": time.time()})
    token_endpoint.responses.append(FakeResponse({"error": "invalid_grant"}, 400))

    with pytest.raises(GraphAuthError, match="has not signed in"):
        resolve_graph_context(PER_USER, tool=make_tool(storage))
    assert store.load("token") is None


def test_refresh_network_error_keeps_the_token(token_endpoint, monkeypatch):
    storage = FakeStorage()
    store = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    store.save("token", {"access_token": "old", "refresh_token": "r", "expires_at": time.time()})
    token_endpoint.responses.append(FakeResponse({"error": "temporarily_unavailable"}, 503))

    with pytest.raises(GraphAuthError, match="503"):
        resolve_graph_context(PER_USER, tool=make_tool(storage))
    assert store.load("token") is not None


def test_callback_rejects_unknown_or_expired_state():
    storage = FakeStorage()
    assert call_callback(storage, {"state": "x" * 43, "code": "c"}).status_code == 400
    assert call_callback(storage, {"state": "../../etc", "code": "c"}).status_code == 400

    storage.set(user_auth.signin_key("s" * 43), json.dumps({"expires_at": time.time() - 1}).encode())
    assert call_callback(storage, {"state": "s" * 43, "code": "c"}).status_code == 400
    assert not storage.exist(user_auth.code_key("s" * 43))


def test_callback_error_is_reported_to_the_tool(token_endpoint):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(sign_in_link(storage, tool)).query)["state"][0]
    call_callback(storage, {"state": state, "error": "access_denied", "error_description": "user declined"})

    with pytest.raises(GraphAuthError, match="user declined"):
        resolve_graph_context(PER_USER, tool=tool)
    # Next request starts a fresh sign-in.
    with pytest.raises(GraphAuthError, match="has not signed in"):
        resolve_graph_context(PER_USER, tool=tool)


def test_mailbox_parameter_is_rejected_and_user_id_is_required():
    storage = FakeStorage()
    with pytest.raises(GraphAuthError, match="Mailbox parameter"):
        resolve_graph_context(PER_USER, mailbox="x@contoso.com", tool=make_tool(storage))
    with pytest.raises(GraphAuthError, match="did not say which user"):
        resolve_graph_context(PER_USER, tool=make_tool(storage, user_id=None))
    with pytest.raises(GraphAuthError, match="Callback URL"):
        resolve_graph_context(dict(PER_USER, redirect_uri=""), tool=make_tool(storage))


def test_sign_out_forgets_the_token(token_endpoint):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(sign_in_link(storage, tool)).query)["state"][0]
    call_callback(storage, {"state": state, "code": "c"})
    resolve_graph_context(PER_USER, tool=tool)

    assert user_sign_in(PER_USER, tool).sign_out() is True
    assert user_sign_in(PER_USER, tool).sign_out() is False
    assert storage.data == {}


def test_china_cloud_uses_china_hosts_and_qualified_scopes():
    storage = FakeStorage()
    creds = dict(PER_USER, cloud="china")
    with pytest.raises(GraphAuthError) as exc:
        resolve_graph_context(creds, tool=make_tool(storage, credentials=creds))
    link = urllib.parse.urlparse(exc.value.args[0].rsplit("\n", 1)[-1])
    scope = urllib.parse.parse_qs(link.query)["scope"][0]
    assert link.netloc == "login.partner.microsoftonline.cn"
    assert "https://microsoftgraph.chinacloudapi.cn/Calendars.ReadWrite" in scope
    assert "offline_access" in scope.split()



def run_sign_out(credentials, storage, user_id="user-1"):
    from tools.outlook_sign_out import SignOutTool

    tool = SignOutTool.__new__(SignOutTool)
    tool.runtime = SimpleNamespace(credentials=credentials, user_id=user_id)
    tool.session = SimpleNamespace(storage=storage)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_variable_message = lambda n, v: ("var", n, v)
    messages = list(tool._invoke({}))
    return [m[1] for m in messages if m[0] == "text"], {m[1]: m[2] for m in messages if m[0] == "var"}


def test_sign_out_tool(token_endpoint):
    storage = FakeStorage()
    user_auth.UserTokenStore(storage, PER_USER, "user-1").save("token", {"access_token": "a", "expires_at": 0})

    texts, out = run_sign_out(PER_USER, storage)
    assert out == {"signed_out": True, "success": True, "error": ""}
    assert storage.data == {}

    texts, out = run_sign_out({"access_token": "shared"}, storage)
    assert out["success"] is False and "Each user signs in" in texts[0]


def test_refresh_without_a_new_refresh_token_keeps_the_old_one(token_endpoint):
    storage = FakeStorage()
    store = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    store.save("token", {"access_token": "old", "refresh_token": "keep-me", "expires_at": time.time()})
    token_endpoint.responses.append(FakeResponse({"access_token": "fresh", "expires_in": 3599}))

    assert resolve_graph_context(PER_USER, tool=make_tool(storage)).access_token == "fresh"
    assert store.load("token")["refresh_token"] == "keep-me"


def test_first_sign_in_records_and_reports_the_account(token_endpoint, monkeypatch):
    monkeypatch.setattr(
        user_auth.requests, "get", lambda url, **kw: FakeResponse({"userPrincipalName": "alice@contoso.com"})
    )
    storage = FakeStorage()
    tool = make_tool(storage)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(sign_in_link(storage, tool)).query)["state"][0]
    call_callback(storage, {"state": state, "code": "c"})

    resolve_graph_context(PER_USER, tool=tool)
    assert tool._signed_in_as == "alice@contoso.com"
    assert user_auth.UserTokenStore(storage, PER_USER, "user-1").load("token")["account"] == "alice@contoso.com"

    # Later calls do not repeat it, and a refresh keeps the account.
    later = make_tool(storage)
    resolve_graph_context(PER_USER, tool=later)
    assert not getattr(later, "_signed_in_as", None)
    store = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    token = store.load("token")
    token["expires_at"] = time.time()
    store.save("token", token)
    resolve_graph_context(PER_USER, tool=later)
    assert store.load("token")["account"] == "alice@contoso.com"

    texts, out = run_sign_out(PER_USER, storage)
    assert "alice@contoso.com" in texts[0]


def test_with_outputs_tells_the_user_which_account_signed_in(monkeypatch):
    from tools import outputs
    from tools.outputs import with_outputs

    monkeypatch.setattr(outputs, "declared_outputs", lambda _: {"success": False, "error": ""})

    class Dummy:
        def create_text_message(self, text):
            return ("text", text)

        def create_variable_message(self, name, value):
            return ("var", name, value)

        @with_outputs
        def _invoke(self, params):
            self._signed_in_as = "bob@contoso.com"
            self._out["success"] = True
            yield self.create_text_message("3 events")

    messages = list(Dummy()._invoke({}))
    texts = [m[1] for m in messages if m[0] == "text"]
    assert texts[0] == "3 events" and "bob@contoso.com" in texts[1]


def test_callback_page_warns_and_cancel_withdraws_the_code(token_endpoint):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(sign_in_link(storage, tool)).query)["state"][0]

    page = call_callback(storage, {"state": state, "code": "victim-code"}).get_data(as_text=True)
    assert "If someone else sent you this link" in page and "cancel=1" in page
    # All styling stays inside the one <style> block (none leaks into the visible page).
    assert page.count("<style>") == page.count("</style>") == 1
    assert page.index(".note{") < page.index("</style>")

    assert call_callback(storage, {"state": state, "cancel": "1"}).status_code == 200
    with pytest.raises(GraphAuthError, match="cancelled"):
        resolve_graph_context(PER_USER, tool=tool)
    assert token_endpoint.calls == []
