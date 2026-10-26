import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]


def load(path):
    spec = importlib.util.spec_from_file_location(path.replace("/", "_"), ROOT / path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def instance(cls):
    o = object.__new__(cls)
    o.runtime = NS(credentials={"access_token": "test"})
    return o


def test_dropbox_honors_expiry():
    m = load("datasources/dropbox_datasource/provider/dropbox.py")
    o = object.__new__(m.DropboxDatasourceProvider)
    account = NS(name=NS(display_name="Test"), email="test@example.test")
    dbx = Mock()
    dbx.users_get_current_account.return_value = account
    r = Mock()
    r.json.return_value = {
        "access_token": "test",
        "expires_in": 14400,
        "refresh_token": "refresh",
    }
    with (
        patch.object(m.requests, "post", return_value=r),
        patch.object(m.dropbox, "Dropbox", return_value=dbx),
    ):
        creds = o._oauth_get_credentials(
            "https://example.test/callback",
            {"client_id": "test", "client_secret": "test"},
            NS(args={"code": "one-time"}),
        )
        assert creds.expires_at > 0
        assert creds.credentials.get("refresh_token") == "refresh"


def test_dropbox_refresh_exchanges_token():
    m = load("datasources/dropbox_datasource/provider/dropbox.py")
    o = object.__new__(m.DropboxDatasourceProvider)
    dbx = Mock()
    dbx.users_get_current_account.return_value = NS(
        name=NS(display_name="Test"), email="test@example.test"
    )
    r = Mock()
    r.json.return_value = {"access_token": "new", "expires_in": 14400}
    with (
        patch.object(m.requests, "post", return_value=r) as post,
        patch.object(m.dropbox, "Dropbox", return_value=dbx),
    ):
        result = o._oauth_refresh_credentials(
            "",
            {"client_id": "test", "client_secret": "test"},
            {"access_token": "expired", "refresh_token": "refresh"},
        )
        assert result.credentials == {"access_token": "new", "refresh_token": "refresh"}
        assert result.expires_at > 0
        assert post.call_args.kwargs["data"]["grant_type"] == "refresh_token"
