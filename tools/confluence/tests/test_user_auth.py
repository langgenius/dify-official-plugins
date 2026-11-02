import json
import time
import urllib.parse
from types import SimpleNamespace

import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from endpoints.signin_callback import SignInCallbackEndpoint
from tests.fakes import OAUTH_BASE, PER_USER, FakeHttp, FakeResponse, FakeStorage
from tools import atlassian, user_auth
from tools.confluence_client import ConfluenceAuthError, is_oauth, is_per_user, resolve_context, user_sign_in

RESOURCES = [
    {"id": "cloud-jira", "url": "https://wiki.atlassian.net", "scopes": ["read:jira-work"]},
    {"id": "cloud-1", "url": "https://acme.atlassian.net", "scopes": ["read:page:confluence", "write:page:confluence"]},
]


def make_tool(storage, user_id="user-1", credentials=PER_USER):
    return SimpleNamespace(
        runtime=SimpleNamespace(credentials=credentials, user_id=user_id),
        session=SimpleNamespace(storage=storage),
    )


@pytest.fixture
def atlassian_http(monkeypatch):
    http = FakeHttp()
    http.on("GET", "/oauth/token/accessible-resources", RESOURCES)
    http.on("GET", "/wiki/rest/api/user/current", {"email": "alice@acme.com", "displayName": "Alice"})
    counter = {"n": 0}

    def token(method, url, **kw):
        counter["n"] += 1
        n = counter["n"]
        http.calls.append(SimpleNamespace(method=method, url=url, **kw))
        if http.token_responses:
            return http.token_responses.pop(0)
        return FakeResponse({"access_token": f"access-{n}", "refresh_token": f"refresh-{n}", "expires_in": 3600})

    http.token_responses = []
    original = http.__call__

    def route(method, url, **kw):
        if url == atlassian.TOKEN_URL:
            return token(method, url, **kw)
        return original(method, url, **kw)

    import requests

    monkeypatch.setattr(requests, "get", lambda url, **kw: route("GET", url, **kw))
    monkeypatch.setattr(requests, "post", lambda url, **kw: route("POST", url, **kw))
    monkeypatch.setattr(requests, "request", route)
    http.token_calls = lambda: [c for c in http.calls if c.url == atlassian.TOKEN_URL]
    return http


def sign_in_link(tool) -> str:
    with pytest.raises(ConfluenceAuthError) as exc:
        resolve_context(tool.runtime.credentials, tool=tool)
    return exc.value.args[0].rsplit("\n", 1)[-1]


def state_of(link: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(link).query)["state"][0]


def call_callback(storage, query: dict):
    request = Request(EnvironBuilder(path="/confluence/callback", query_string=query).get_environ())
    return SignInCallbackEndpoint(SimpleNamespace(storage=storage)).invoke(request, {}, {})


def test_modes():
    assert is_per_user(PER_USER) and not is_oauth(PER_USER)
    assert is_oauth({"access_token": "x"}) and not is_per_user({"access_token": "x", "auth_mode": "per_user"})
    assert not is_per_user({"url": "https://wiki", "token": "t"})


def test_first_call_returns_an_atlassian_sign_in_link(atlassian_http):
    storage = FakeStorage()
    link = sign_in_link(make_tool(storage))
    parsed = urllib.parse.urlparse(link)
    query = urllib.parse.parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == atlassian.AUTHORIZE_URL
    assert query["audience"] == ["api.atlassian.com"]
    assert query["prompt"] == ["consent"]
    assert query["redirect_uri"] == [PER_USER["redirect_uri"]]
    assert query["client_id"] == ["app-id"]
    scopes = set(query["scope"][0].split())
    assert {"read:page:confluence", "write:page:confluence", "read:space:confluence", "offline_access"} <= scopes
    # No User identity API scope: the account name comes from Confluence's current user.
    assert "read:me" not in scopes
    assert storage.exist(user_auth.signin_key(query["state"][0]))
    assert atlassian_http.token_calls() == []


def test_full_sign_in_then_cached_then_refreshed(atlassian_http):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))

    with pytest.raises(ConfluenceAuthError, match="not been completed"):
        resolve_context(PER_USER, tool=tool)

    assert call_callback(storage, {"state": state, "code": "auth-code"}).status_code == 200

    ctx = resolve_context(PER_USER, tool=tool)
    assert ctx.base_url == OAUTH_BASE
    assert ctx.headers["Authorization"] == "Bearer access-1"
    assert ctx.cloud and ctx.site_url == "https://acme.atlassian.net"
    assert tool._signed_in_as == "alice@acme.com"
    redeem = atlassian_http.token_calls()[0]
    assert redeem.json == {
        "grant_type": "authorization_code", "code": "auth-code", "redirect_uri": PER_USER["redirect_uri"],
        "client_id": "app-id", "client_secret": "s3cret",
    }
    # The sign-in records are gone once redeemed.
    assert not any(k.startswith("signin/") for k in storage.data)

    # Cached: no new token request.
    tool2 = make_tool(storage)
    assert resolve_context(PER_USER, tool=tool2).headers["Authorization"] == "Bearer access-1"
    assert len(atlassian_http.token_calls()) == 1
    assert not getattr(tool2, "_signed_in_as", None)

    # Expired: refreshed with the rotating refresh token, site kept.
    record = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    token = record.load("token")
    token["expires_at"] = time.time() - 1
    record.save("token", token)
    ctx = resolve_context(PER_USER, tool=make_tool(storage))
    assert ctx.headers["Authorization"] == "Bearer access-2"
    assert ctx.base_url == OAUTH_BASE
    refresh = atlassian_http.token_calls()[1]
    assert refresh.json["grant_type"] == "refresh_token" and refresh.json["refresh_token"] == "refresh-1"
    assert record.load("token")["refresh_token"] == "refresh-2"


def test_tokens_are_encrypted_and_per_user(atlassian_http):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    call_callback(storage, {"state": state, "code": "c"})
    resolve_context(PER_USER, tool=tool)
    blobs = b"".join(storage.data.values())
    assert b"access-1" not in blobs and b"refresh-1" not in blobs and b"cloud-1" not in blobs
    # Another user gets their own link.
    other = make_tool(storage, user_id="user-2")
    assert "not signed in" in str(pytest.raises(ConfluenceAuthError, resolve_context, PER_USER, tool=other).value)
    # Another client secret cannot read the token: that user is simply signed out.
    rotated = {**PER_USER, "client_secret": "new"}
    with pytest.raises(ConfluenceAuthError, match="not signed in"):
        resolve_context(rotated, tool=make_tool(storage, credentials=rotated))


def test_revoked_refresh_token_starts_a_new_sign_in(atlassian_http):
    storage = FakeStorage()
    tool = make_tool(storage)
    call_callback(storage, {"state": state_of(sign_in_link(tool)), "code": "c"})
    resolve_context(PER_USER, tool=tool)
    record = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    token = record.load("token")
    token["expires_at"] = 0
    record.save("token", token)
    atlassian_http.token_responses.append(FakeResponse({"error": "unauthorized_client"}, 403))
    with pytest.raises(ConfluenceAuthError, match="not signed in to Atlassian yet"):
        resolve_context(PER_USER, tool=make_tool(storage))
    assert record.load("token") is None


def test_site_url_picks_among_several_sites(atlassian_http):
    assert atlassian.pick_site(RESOURCES)["cloud_id"] == "cloud-1"
    assert atlassian.pick_site(RESOURCES, "wiki.atlassian.net")["cloud_id"] == "cloud-jira"
    assert atlassian.pick_site(RESOURCES, "https://ACME.atlassian.net/wiki/spaces/DEV")["cloud_id"] == "cloud-1"
    with pytest.raises(atlassian.AtlassianAuthError, match="no access to https://other.atlassian.net"):
        atlassian.pick_site(RESOURCES, "other.atlassian.net")
    with pytest.raises(atlassian.AtlassianAuthError, match="did not grant access to any site"):
        atlassian.pick_site([])


def test_custom_scopes_always_include_offline_access():
    assert atlassian.scope({"scopes": "read:page:confluence, read:me"}) == "read:page:confluence read:me offline_access"
    assert atlassian.scope({}) == atlassian.DEFAULT_SCOPE


def test_callback_rejects_unknown_and_expired_states():
    storage = FakeStorage()
    assert call_callback(storage, {"state": "x" * 43, "code": "c"}).status_code == 400
    state = "s" * 43
    storage.set(user_auth.signin_key(state), json.dumps({"expires_at": time.time() - 1}).encode())
    assert call_callback(storage, {"state": state, "code": "c"}).status_code == 400
    assert not storage.exist(user_auth.code_key(state))


def test_callback_error_and_cancel_reach_the_tool(atlassian_http):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    page = call_callback(storage, {"state": state, "error": "access_denied", "error_description": "User denied"})
    assert page.status_code == 400 and b"Atlassian reported" in page.data
    with pytest.raises(ConfluenceAuthError, match="User denied"):
        resolve_context(PER_USER, tool=tool)

    state = state_of(sign_in_link(tool))
    page = call_callback(storage, {"state": state, "code": "c"})
    assert b"cancel this sign-in" in page.data
    assert b"Atlassian account was not connected" in call_callback(storage, {"state": state, "cancel": "1"}).data
    with pytest.raises(ConfluenceAuthError, match="cancelled"):
        resolve_context(PER_USER, tool=tool)
    assert atlassian_http.token_calls() == []


def test_sign_out_forgets_the_token(atlassian_http):
    storage = FakeStorage()
    tool = make_tool(storage)
    call_callback(storage, {"state": state_of(sign_in_link(tool)), "code": "c"})
    resolve_context(PER_USER, tool=tool)
    sign_in = user_sign_in(PER_USER, tool)
    assert sign_in.account() == "alice@acme.com"
    assert sign_in.sign_out() is True
    assert sign_in.sign_out() is False
    assert storage.data == {}


def test_missing_user_or_callback_url_is_reported():
    with pytest.raises(ConfluenceAuthError, match="did not say which user"):
        resolve_context(PER_USER, tool=make_tool(FakeStorage(), user_id=None))
    no_url = {**PER_USER, "redirect_uri": ""}
    with pytest.raises(ConfluenceAuthError, match="Sign-in Callback URL"):
        resolve_context(no_url, tool=make_tool(FakeStorage(), credentials=no_url))


def test_app_fields_without_a_token_mean_per_user_even_if_mode_was_left_on_token():
    left_on_token = {**PER_USER, "auth_mode": "token"}
    assert is_per_user(left_on_token)
    assert not is_per_user({**left_on_token, "token": "t"})
    assert not is_per_user({"auth_mode": "token", "url": "https://wiki", "token": "t"})
