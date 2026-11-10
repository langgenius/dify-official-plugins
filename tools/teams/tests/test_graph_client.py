import pytest

from tools.graph_client import (
    CLOUDS,
    GraphError,
    resolve_graph_context,
    segment,
    split_list,
    to_graph_datetime,
)


def test_credentials_without_a_cloud_stay_on_global_graph():
    ctx = resolve_graph_context({"access_token": "t", "refresh_token": "r"})
    assert ctx.api_base == "https://graph.microsoft.com/v1.0"


@pytest.mark.parametrize("cloud", ["usgov", "dod", "china"])
def test_credentials_follow_their_national_cloud(cloud):
    host = CLOUDS[cloud][1]
    ctx = resolve_graph_context({"access_token": "t", "graph_base_url": host})
    assert ctx.api_base == f"{host}/v1.0"
    assert ctx.graph_host == host


def test_token_is_never_sent_to_an_unknown_host():
    with pytest.raises(GraphError, match="Unsupported"):
        resolve_graph_context({"access_token": "t", "graph_base_url": "https://evil.example"})


def test_missing_token():
    with pytest.raises(GraphError, match="Access token is required"):
        resolve_graph_context({})


def test_segment_quotes_teams_ids():
    assert segment("19:abc@thread.tacv2") == "19%3Aabc%40thread.tacv2"
    assert segment(" a/b ") == "a%2Fb"


def test_split_list():
    assert split_list("a@x.com, b@x.com\nc@x.com,,") == ["a@x.com", "b@x.com", "c@x.com"]
    assert split_list(None) == []


@pytest.mark.parametrize(
    "value, expected, assumed",
    [
        ("2026-12-01T10:00:00+09:00", "2026-12-01T01:00:00Z", False),
        ("2026-12-01T10:00:00Z", "2026-12-01T10:00:00Z", False),
        ("2026-12-01T10:00:00", "2026-12-01T10:00:00Z", True),
        ("2026-12-01", "2026-12-01T00:00:00Z", True),
    ],
)
def test_to_graph_datetime(value, expected, assumed):
    assert to_graph_datetime(value, "x") == (expected, assumed)


def test_to_graph_datetime_rejects_garbage():
    with pytest.raises(GraphError, match="ISO 8601"):
        to_graph_datetime("next tuesday", "due_datetime")
