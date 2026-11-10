import json
from types import SimpleNamespace
from typing import Any

PER_USER = {
    "auth_mode": "per_user",
    "client_id": "app-id",
    "client_secret": "s3cret",
    "redirect_uri": "https://dify.example.com/e/hook/confluence/callback",
}
OAUTH = {"access_token": "oauth-token", "cloud_id": "cloud-1", "site_url": "https://acme.atlassian.net"}
CLOUD_TOKEN = {"url": "https://acme.atlassian.net/wiki", "username": "me@acme.com", "token": "api-token"}
SERVER_TOKEN = {"url": "https://wiki.example.com/confluence/", "token": "pat"}

OAUTH_BASE = "https://api.atlassian.com/ex/confluence/cloud-1"


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
    def __init__(self, payload: Any = None, status_code: int = 200, content: bytes | None = None):
        self._payload = payload
        self.status_code = status_code
        if content is not None:
            self.content = content
        else:
            self.content = b"" if payload is None else json.dumps(payload).encode()
        self.text = self.content.decode(errors="replace")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeHttp:
    """Answers requests by (method, URL suffix); records every call."""

    def __init__(self):
        self.routes: list[tuple[str, str, Any]] = []
        self.calls: list[SimpleNamespace] = []

    def on(self, method: str, url_part: str, *responses: Any) -> "FakeHttp":
        for response in responses:
            self.routes.append((method, url_part, response))
        return self

    def __call__(self, method, url, **kwargs):
        self.calls.append(SimpleNamespace(method=method, url=url, **kwargs))
        for i, (m, part, response) in enumerate(self.routes):
            if m == method and part in url:
                # The last response for a route repeats; earlier ones are used once.
                if sum(1 for r in self.routes if r[0] == m and r[1] == part) > 1:
                    self.routes.pop(i)
                return response if isinstance(response, FakeResponse) else FakeResponse(response)
        return FakeResponse({"errorMessages": [f"no route for {method} {url}"]}, 404)

    def install(self, monkeypatch):
        import requests

        monkeypatch.setattr(requests, "request", self)
        monkeypatch.setattr(requests, "get", lambda url, **kw: self("GET", url, **kw))
        monkeypatch.setattr(requests, "post", lambda url, **kw: self("POST", url, **kw))
        return self


def make_tool(tool_class, credentials, storage=None, user_id="user-1"):
    tool = tool_class.__new__(tool_class)
    tool.runtime = SimpleNamespace(credentials=credentials, user_id=user_id)
    tool.session = SimpleNamespace(storage=storage or FakeStorage())
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_variable_message = lambda name, value: ("var", name, value)
    tool.create_blob_message = lambda blob, meta=None: ("blob", blob, meta)
    return tool


def run(tool, params=None):
    messages = list(tool._invoke(params or {}))
    variables = {m[1]: m[2] for m in messages if m[0] == "var"}
    texts = [m[1] for m in messages if m[0] == "text"]
    jsons = [m[1] for m in messages if m[0] == "json"]
    blobs = [m for m in messages if m[0] == "blob"]
    return SimpleNamespace(messages=messages, vars=variables, texts=texts, json=jsons, blobs=blobs)
