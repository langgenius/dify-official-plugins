from types import SimpleNamespace

import pytest
from dify_plugin.entities.invoke_message import InvokeMessage
from dify_plugin.entities.tool import ToolRuntime

from tests.fakes import FakeHttp, OAUTH
from tools.search_events import SearchEventsTool


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def search(http, events, query="north", **params):
    http.on("GET", "/calendars/primary/events", {
        "items": events, "nextPageToken": "next-page", "timeZone": "UTC"
    })
    tool = SearchEventsTool(
        runtime=ToolRuntime(credentials=OAUTH, user_id="user-1", session_id="test-session"),
        session=SimpleNamespace(),
    )
    # Keep the actual SDK message constructors, including serialization/validation.
    messages = list(tool.invoke({"query": query, **params}))
    for message in messages:
        message.model_dump_json()
    results = [m.message.json_object for m in messages if m.type == InvokeMessage.MessageType.JSON]
    assert len(results) == 1
    return results[0]


@pytest.mark.parametrize("match", [
    {"organizer": {"email": "north@example.com"}},
    {"organizer": {"displayName": "North Team"}},
    {"eventType": "workingLocation", "workingLocationProperties": {"type": "officeLocation", "officeLocation": {"buildingId": "north"}}},
    {"eventType": "workingLocation", "workingLocationProperties": {"type": "officeLocation", "officeLocation": {"deskId": "north"}}},
    {"eventType": "workingLocation", "workingLocationProperties": {"type": "officeLocation", "officeLocation": {"label": "north"}}},
    {"eventType": "workingLocation", "workingLocationProperties": {"type": "customLocation", "customLocation": {"label": "north"}}},
])
def test_preserves_server_matches_outside_locally_scored_fields(http, match):
    result = search(http, [{"id": "match", "summary": "Planning", **match}])
    assert result["total_count"] == 1
    assert result["events"][0]["id"] == "match"
    assert result["events"][0]["relevance_score"] == 0
    assert result["next_page_token"] == "next-page"
    assert http.calls[0].params["q"] == "north"


def test_preserves_translated_working_location_matches(http):
    # Google also matches predefined keywords in translated working-location titles.
    result = search(http, [{"id": "office", "summary": "Office", "eventType": "workingLocation",
                           "workingLocationProperties": {"type": "officeLocation"}}], query="Bureau")
    assert result["total_count"] == 1
    assert result["events"][0]["id"] == "office"


def test_ranks_visible_matches_without_discarding_other_server_matches(http):
    result = search(http, [
        {"id": "organizer", "organizer": {"email": "north@example.com"}},
        {"id": "title", "summary": "North planning"},
        {"id": "building", "eventType": "workingLocation", "workingLocationProperties": {"type": "officeLocation", "officeLocation": {"buildingId": "north"}}},
        {"id": "description", "description": "north"},
    ])
    assert [e["id"] for e in result["events"]] == ["title", "description", "organizer", "building"]
    assert [e["relevance_score"] for e in result["events"]] == [15, 5, 0, 0]
    assert result["total_count"] == 4


def test_empty_server_results_remain_empty(http):
    result = search(http, [])
    assert result["total_count"] == 0
    assert result["events"] == []
