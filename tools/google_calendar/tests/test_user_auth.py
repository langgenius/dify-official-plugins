import json
import time
import urllib.parse
from types import SimpleNamespace

import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from endpoints.signin_callback import SignInCallbackEndpoint
from tests.fakes import OAUTH, PER_USER, FakeHttp, FakeResponse, FakeStorage
from tools import user_auth
from tools.google_client import GoogleAuthError, google_request, is_per_user, resolve_context, user_sign_in

CALENDAR = "https://www.googleapis.com/auth/calendar"


def make_tool(storage, user_id="user-1", credentials=PER_USER):
    return SimpleNamespace(runtime=SimpleNamespace(credentials=credentials, user_id=user_id), session=SimpleNamespace(storage=storage))


@pytest.fixture
def google(monkeypatch):
    http = FakeHttp().install(monkeypatch)
    http.on("GET", user_auth.USERINFO_URL, {"email": "alice@example.com"})
    counter = {"n": 0}
    http.token_responses = []
    original = http.__call__

    def route(method, url, **kw):
        if url == user_auth.TOKEN_URL:
            http.calls.append(SimpleNamespace(method=method, url=url, **kw))
            if http.token_responses:
                return http.token_responses.pop(0)
            counter["n"] += 1
            n = counter["n"]
            body = {"access_token": f"access-{n}", "expires_in": 3599, "scope": f"openid email {CALENDAR}"}
            if kw.get("data", {}).get("grant_type") == "authorization_code":
                body["refresh_token"] = "refresh-1"
            return FakeResponse(body)
        return original(method, url, **kw)

    import requests

    monkeypatch.setattr(requests, "get", lambda url, **kw: route("GET", url, **kw))
    monkeypatch.setattr(requests, "post", lambda url, **kw: route("POST", url, **kw))
    monkeypatch.setattr(requests, "request", route)
    http.token_calls = lambda: [c for c in http.calls if c.url == user_auth.TOKEN_URL]
    return http


def sign_in_link(tool) -> str:
    with pytest.raises(GoogleAuthError) as exc:
        resolve_context(tool.runtime.credentials, tool=tool)
    return exc.value.args[0].rsplit("\n", 1)[-1]


def state_of(link: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(link).query)["state"][0]


def call_callback(storage, query):
    request = Request(EnvironBuilder(path="/google_calendar/callback", query_string=query).get_environ())
    return SignInCallbackEndpoint(SimpleNamespace(storage=storage)).invoke(request, {}, {})


def signed_in(google, storage):
    tool = make_tool(storage)
    call_callback(storage, {"state": state_of(sign_in_link(tool)), "code": "c"})
    resolve_context(PER_USER, tool=tool)
    return tool


def test_modes():
    assert is_per_user(PER_USER) and not is_per_user(OAUTH)
    assert is_per_user({k: v for k, v in PER_USER.items() if k != "auth_mode"})
    assert not is_per_user({**PER_USER, "access_token": "x"})


def test_first_call_returns_a_google_link_with_pkce_and_offline_access(google):
    storage = FakeStorage()
    link = sign_in_link(make_tool(storage))
    parsed = urllib.parse.urlparse(link)
    q = urllib.parse.parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == user_auth.AUTHORIZE_URL
    assert q["access_type"] == ["offline"] and "consent" in q["prompt"][0]
    assert q["code_challenge_method"] == ["S256"] and q["redirect_uri"] == [PER_USER["redirect_uri"]]
    assert q["scope"][0].split() == ["openid", "email", CALENDAR]
    assert storage.exist(user_auth.signin_key(q["state"][0])) and google.calls == []


def test_full_sign_in_cached_and_refreshed(google):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    with pytest.raises(GoogleAuthError, match="not been completed"):
        resolve_context(PER_USER, tool=tool)
    assert call_callback(storage, {"state": state, "code": "auth-code"}).status_code == 200

    ctx = resolve_context(PER_USER, tool=tool)
    assert ctx.access_token == "access-1" and tool._signed_in_as == "alice@example.com"
    redeem = google.token_calls()[0]
    assert redeem.data["grant_type"] == "authorization_code" and redeem.data["code"] == "auth-code"
    assert redeem.data["code_verifier"] and redeem.data["client_secret"] == "s3cret"
    assert not any(k.startswith("signin/") for k in storage.data)
    assert b"access-1" not in b"".join(storage.data.values())

    assert resolve_context(PER_USER, tool=make_tool(storage)).access_token == "access-1"
    record = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    token = record.load("token")
    token["expires_at"] = time.time() - 1
    record.save("token", token)
    # Google does not return a new refresh token on refresh: the old one is kept.
    assert resolve_context(PER_USER, tool=make_tool(storage)).access_token == "access-2"
    assert google.token_calls()[1].data == {"grant_type": "refresh_token", "refresh_token": "refresh-1",
                                             "client_id": PER_USER["client_id"], "client_secret": "s3cret"}
    assert record.load("token")["refresh_token"] == "refresh-1"


def test_unticked_permission_is_refused(google):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    call_callback(storage, {"state": state, "code": "c"})
    google.token_responses.append(FakeResponse({"access_token": "a", "refresh_token": "r", "scope": "openid email"}))
    with pytest.raises(GoogleAuthError, match="did not grant every permission"):
        resolve_context(PER_USER, tool=tool)


def test_invalid_grant_starts_a_new_sign_in(google):
    storage = FakeStorage()
    signed_in(google, storage)
    record = user_auth.UserTokenStore(storage, PER_USER, "user-1")
    token = record.load("token")
    token["expires_at"] = 0
    record.save("token", token)
    google.token_responses.append(FakeResponse({"error": "invalid_grant", "error_description": "Token has been expired or revoked."}, 400))
    with pytest.raises(GoogleAuthError, match="not signed in to Google yet"):
        resolve_context(PER_USER, tool=make_tool(storage))
    assert record.load("token") is None


def test_revoked_access_token_gets_a_new_link(google):
    storage = FakeStorage()
    tool = signed_in(google, storage)
    ctx = resolve_context(PER_USER, tool=tool)
    google.on("GET", "/calendars/primary", FakeResponse({"error": {"message": "Invalid Credentials"}}, 401))
    with pytest.raises(GoogleAuthError, match="not signed in to Google yet"):
        google_request(ctx, "GET", "https://www.googleapis.com/calendar/v3/calendars/primary")


def test_per_user_isolation_and_secret_rotation(google):
    storage = FakeStorage()
    signed_in(google, storage)
    with pytest.raises(GoogleAuthError, match="not signed in"):
        resolve_context(PER_USER, tool=make_tool(storage, user_id="user-2"))
    rotated = {**PER_USER, "client_secret": "new"}
    with pytest.raises(GoogleAuthError, match="not signed in"):
        resolve_context(rotated, tool=make_tool(storage, credentials=rotated))


def test_callback_errors_and_cancel(google):
    storage = FakeStorage()
    assert call_callback(storage, {"state": "x" * 43, "code": "c"}).status_code == 400
    state = "s" * 43
    storage.set(user_auth.signin_key(state), json.dumps({"expires_at": time.time() - 1}).encode())
    assert call_callback(storage, {"state": state, "code": "c"}).status_code == 400

    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    page = call_callback(storage, {"state": state, "error": "access_denied"})
    assert page.status_code == 400 and b"Google reported" in page.data
    with pytest.raises(GoogleAuthError, match="access_denied"):
        resolve_context(PER_USER, tool=tool)
    state = state_of(sign_in_link(tool))
    assert b"Google account was not connected" in call_callback(storage, {"state": state, "cancel": "1"}).data
    with pytest.raises(GoogleAuthError, match="cancelled"):
        resolve_context(PER_USER, tool=tool)


def test_sign_out(google):
    storage = FakeStorage()
    tool = signed_in(google, storage)
    sign_in = user_sign_in(PER_USER, tool)
    assert sign_in.account() == "alice@example.com"
    assert sign_in.sign_out() is True and sign_in.sign_out() is False and storage.data == {}


def test_scope_override_keeps_openid_email():
    assert user_auth.scope({"scopes": CALENDAR + ".readonly"}) == f"email openid {CALENDAR}.readonly"
