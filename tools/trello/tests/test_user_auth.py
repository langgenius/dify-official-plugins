import json
import time
import urllib.parse
from types import SimpleNamespace

import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from endpoints.signin_callback import SignInCallbackEndpoint
from endpoints.signin_token import SignInTokenEndpoint
from tests.fakes import PER_USER, TOKEN, FakeHttp, FakeResponse, FakeStorage
from tools import user_auth
from tools.trello_client import TrelloAuthError, is_per_user, resolve_context, trello_request, user_sign_in

USER_TOKEN = "a" * 64


def make_tool(storage, user_id="user-1", credentials=PER_USER):
    return SimpleNamespace(runtime=SimpleNamespace(credentials=credentials, user_id=user_id),
                           session=SimpleNamespace(storage=storage))


@pytest.fixture
def http(monkeypatch):
    http = FakeHttp().install(monkeypatch)
    http.on("GET", "/members/me", {"id": "m1", "username": "alice", "fullName": "Alice Doe"})
    return http


def sign_in_link(tool) -> str:
    with pytest.raises(TrelloAuthError) as exc:
        resolve_context(tool.runtime.credentials, tool=tool)
    return exc.value.args[0].rsplit("\n", 1)[-1]


def state_of(link: str) -> str:
    return_url = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)["return_url"][0]
    return urllib.parse.parse_qs(urllib.parse.urlparse(return_url).query)["state"][0]


def get_callback(storage, query):
    request = Request(EnvironBuilder(path="/trello/callback", query_string=query).get_environ())
    return SignInCallbackEndpoint(SimpleNamespace(storage=storage)).invoke(request, {}, {})


def post_token(storage, state, token=USER_TOKEN):
    request = Request(EnvironBuilder(path="/trello/callback", method="POST", query_string={"state": state},
                                     data=json.dumps({"token": token}), content_type="application/json").get_environ())
    return SignInTokenEndpoint(SimpleNamespace(storage=storage)).invoke(request, {}, {})


def test_modes():
    assert is_per_user(PER_USER)
    assert not is_per_user(TOKEN)
    # The Mode select left on its default while the per-user fields are filled in.
    assert is_per_user({**PER_USER, "auth_mode": "token"})
    assert not is_per_user({**PER_USER, "auth_mode": "token", "trello_api_token": "t"})


def test_first_call_returns_a_trello_authorize_link(http):
    storage = FakeStorage()
    link = sign_in_link(make_tool(storage))
    parsed = urllib.parse.urlparse(link)
    query = urllib.parse.parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == user_auth.AUTHORIZE_URL
    assert query["key"] == ["app-key"] and query["response_type"] == ["token"] and query["scope"] == ["read,write"]
    assert query["expiration"] == ["30days"] and query["callback_method"] == ["fragment"]
    assert query["return_url"][0].startswith(PER_USER["redirect_uri"] + "?state=")
    issued = json.loads(storage.get(user_auth.signin_key(state_of(link))))
    assert "BEGIN PUBLIC KEY" in issued["public_key"]
    assert http.calls == []


def test_full_sign_in_with_sealed_token(http):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))

    with pytest.raises(TrelloAuthError, match="not been completed"):
        resolve_context(PER_USER, tool=tool)

    page = get_callback(storage, {"state": state})
    assert page.status_code == 200 and b"location.hash" in page.data and b"cancel this sign-in" in page.data
    assert post_token(storage, state).status_code == 200
    # Only the sealed token is stored by the endpoint; it cannot be read back without the tool's private key.
    assert USER_TOKEN.encode() not in b"".join(storage.data.values())
    # A link is used once.
    assert post_token(storage, state, "b" * 64).status_code == 409

    ctx = resolve_context(PER_USER, tool=tool)
    assert ctx.token == USER_TOKEN and tool._signed_in_as == "Alice Doe (@alice)"
    assert http.calls[0].headers["Authorization"] == f'OAuth oauth_consumer_key="app-key", oauth_token="{USER_TOKEN}"'
    assert not any(k.startswith("signin/") for k in storage.data)
    assert USER_TOKEN.encode() not in b"".join(storage.data.values())

    # Cached for the next request, and not announced again.
    tool2 = make_tool(storage)
    assert resolve_context(PER_USER, tool=tool2).token == USER_TOKEN and not getattr(tool2, "_signed_in_as", None)


def test_rejected_token_starts_a_new_sign_in(http):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    post_token(storage, state)
    ctx = resolve_context(PER_USER, tool=tool)
    http.on("GET", "/boards/b1", FakeResponse({"message": "invalid token"}, 401))
    with pytest.raises(TrelloAuthError, match="expired or was revoked"):
        trello_request(ctx, "GET", "boards/b1")
    with pytest.raises(TrelloAuthError, match="not been completed"):
        resolve_context(PER_USER, tool=make_tool(storage))


def test_token_check_failure_is_reported(http):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    post_token(storage, state)
    http.routes.clear()
    http.on("GET", "/members/me", FakeResponse({}, 401))
    with pytest.raises(TrelloAuthError, match="did not accept"):
        resolve_context(PER_USER, tool=tool)


def test_endpoints_reject_bad_states_and_tokens():
    storage = FakeStorage()
    assert get_callback(storage, {"state": "x" * 43}).status_code == 400
    assert post_token(storage, "x" * 43).status_code == 400
    state = "s" * 43
    storage.set(user_auth.signin_key(state), json.dumps({"expires_at": time.time() - 1, "public_key": "k"}).encode())
    assert get_callback(storage, {"state": state}).status_code == 400
    assert post_token(storage, state).status_code == 400


def test_post_rejects_malformed_token(http):
    storage = FakeStorage()
    state = state_of(sign_in_link(make_tool(storage)))
    assert post_token(storage, state, "not a token!").status_code == 400
    assert post_token(storage, state, "").status_code == 400


def test_cancel_reaches_the_tool(http):
    storage = FakeStorage()
    tool = make_tool(storage)
    state = state_of(sign_in_link(tool))
    assert b"was not connected" in get_callback(storage, {"state": state, "cancel": "1"}).data
    with pytest.raises(TrelloAuthError, match="cancelled"):
        resolve_context(PER_USER, tool=tool)


def test_tokens_are_per_user_and_tied_to_the_secret(http):
    storage = FakeStorage()
    tool = make_tool(storage)
    post_token(storage, state_of(sign_in_link(tool)))
    resolve_context(PER_USER, tool=tool)
    with pytest.raises(TrelloAuthError, match="not signed in to Trello yet"):
        resolve_context(PER_USER, tool=make_tool(storage, user_id="user-2"))
    rotated = {**PER_USER, "trello_api_secret": "new"}
    with pytest.raises(TrelloAuthError, match="not signed in to Trello yet"):
        resolve_context(rotated, tool=make_tool(storage, credentials=rotated))


def test_sign_out(http):
    storage = FakeStorage()
    tool = make_tool(storage)
    post_token(storage, state_of(sign_in_link(tool)))
    resolve_context(PER_USER, tool=tool)
    sign_in = user_sign_in(PER_USER, tool)
    assert sign_in.account() == "Alice Doe (@alice)"
    assert sign_in.sign_out() is True and sign_in.sign_out() is False
    assert storage.data == {}


def test_missing_user_or_callback_url():
    with pytest.raises(TrelloAuthError, match="did not say which user"):
        resolve_context(PER_USER, tool=make_tool(FakeStorage(), user_id=None))
    no_url = {**PER_USER, "redirect_uri": ""}
    with pytest.raises(TrelloAuthError, match="Sign-in Callback URL"):
        resolve_context(no_url, tool=make_tool(FakeStorage(), credentials=no_url))
