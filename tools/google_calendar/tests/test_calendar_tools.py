import importlib
import inspect
from pathlib import Path

import pytest
import yaml
from dify_plugin import Tool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.google_calendar import GoogleCalendarProvider
from tests.fakes import API, OAUTH, PER_USER, FakeHttp, FakeResponse, make_tool, run
from tools.google_calendar_check_availability import GoogleCalendarCheckAvailabilityTool
from tools.google_calendar_delete_event import GoogleCalendarDeleteEventTool
from tools.google_calendar_get_event import GoogleCalendarGetEventTool
from tools.google_calendar_sign_out import SignOutTool
from tools.google_calendar_update_event import GoogleCalendarUpdateEventTool
from tools.list_calendars import ListCalendarsTool

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "google_calendar.yaml").read_text(encoding="utf-8"))
EVENT = {"id": "e1", "summary": "Standup", "start": {"dateTime": "2026-11-03T10:00:00+09:00", "timeZone": "Asia/Tokyo"},
         "end": {"dateTime": "2026-11-03T10:15:00+09:00", "timeZone": "Asia/Tokyo"}, "location": "Room 1",
         "attendees": [{"email": "bob@example.com", "responseStatus": "accepted"}], "hangoutLink": "https://meet.google.com/abc",
         "organizer": {"email": "alice@example.com"}, "htmlLink": "https://calendar.google.com/event?eid=1"}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def test_get_event(http):
    http.on("GET", "/calendars/primary/events/e1", EVENT)
    result = run(make_tool(GoogleCalendarGetEventTool, OAUTH), {"event_id": "e1"})
    assert result.vars["title"] == "Standup" and result.vars["event"]["meeting_link"] == "https://meet.google.com/abc"
    assert "join: https://meet.google.com/abc" in result.texts[-1]
    assert http.calls[0].headers["Authorization"] == "Bearer oauth-token"


def test_update_event_patches_only_given_fields_and_adds_guests(http):
    http.on("GET", "/events/e1", EVENT)
    http.on("PATCH", "/events/e1", {**EVENT, "summary": "Daily"})
    result = run(make_tool(GoogleCalendarUpdateEventTool, OAUTH),
                 {"event_id": "e1", "title": "Daily", "start_time": "2026-11-04T10:00:00", "attendees": "carol@example.com, bob@example.com",
                  "send_updates": "none"})
    assert result.vars["success"], result.texts
    patch = http.calls[1].json
    # A time without an offset takes the event's own time zone.
    assert patch["start"] == {"dateTime": "2026-11-04T10:00:00", "timeZone": "Asia/Tokyo"}
    assert [a["email"] for a in patch["attendees"]] == ["bob@example.com", "carol@example.com"]
    assert patch["summary"] == "Daily" and http.calls[1].params == {"sendUpdates": "none"}


def test_update_all_day_end_is_exclusive(http):
    http.on("GET", "/events/e1", {"id": "e1", "start": {"date": "2026-11-03"}, "end": {"date": "2026-11-04"}})
    http.on("PATCH", "/events/e1", {"id": "e1"})
    run(make_tool(GoogleCalendarUpdateEventTool, OAUTH), {"event_id": "e1", "start_time": "2026-12-24"})
    assert http.calls[1].json == {"start": {"date": "2026-12-24"}, "end": {"date": "2026-12-25"}}


def test_update_needs_an_offset_or_time_zone(http):
    http.on("GET", "/events/e2", {"id": "e2", "start": {"dateTime": "2026-11-03T10:00:00Z"}})
    result = run(make_tool(GoogleCalendarUpdateEventTool, OAUTH), {"event_id": "e2", "start_time": "2026-11-04T10:00:00"})
    assert "no UTC offset" in result.vars["error"]
    nothing = run(make_tool(GoogleCalendarUpdateEventTool, OAUTH), {"event_id": "e2"})
    assert "Nothing to update" in nothing.vars["error"]


def test_delete_event_and_calendar_ids_are_encoded(http):
    http.on("DELETE", "/events/e1", FakeResponse(None, 204))
    result = run(make_tool(GoogleCalendarDeleteEventTool, OAUTH), {"event_id": "e1", "calendar_id": "team@group.calendar.google.com"})
    assert result.vars["deleted"] is True
    assert http.calls[0].url == f"{API}/calendars/team%40group.calendar.google.com/events/e1"
    run(make_tool(GoogleCalendarGetEventTool, OAUTH), {"event_id": "../../users/me"})
    assert http.calls[-1].url == f"{API}/calendars/primary/events/..%2F..%2Fusers%2Fme"


def test_check_availability(http):
    http.on("POST", "/freeBusy", {"calendars": {
        "primary": {"busy": [{"start": "2026-11-03T01:00:00Z", "end": "2026-11-03T02:00:00Z"}]},
        "bob@example.com": {"errors": [{"reason": "notFound"}]}}})
    result = run(make_tool(GoogleCalendarCheckAvailabilityTool, OAUTH),
                 {"time_min": "2026-11-03T00:00:00Z", "time_max": "2026-11-04T00:00:00Z", "calendar_ids": "primary, bob@example.com"})
    assert result.vars["free"] is False and len(result.vars["busy"]) == 1
    assert http.calls[0].json["items"] == [{"id": "primary"}, {"id": "bob@example.com"}]
    assert "Could not read: bob@example.com: notFound" in result.texts[-1]


def test_original_tool_with_oauth_and_per_user(http):
    http.on("GET", "/users/me/calendarList", {"items": [{"id": "primary", "summary": "Alice"}]})
    result = run(make_tool(ListCalendarsTool, OAUTH))
    assert http.calls[0].headers["Authorization"] == "Bearer oauth-token" and result.json
    per_user = run(make_tool(ListCalendarsTool, PER_USER))
    assert "https://accounts.google.com/o/oauth2/v2/auth?" in per_user.texts[0]


def test_sign_out_modes(http):
    assert "only applies" in run(make_tool(SignOutTool, OAUTH)).texts[0]
    assert run(make_tool(SignOutTool, PER_USER)).vars == {"signed_out": False, "success": True, "error": ""}


# ── plugin ────────────────────────────────────────────────────────────


def tool_class(spec):
    module = importlib.import_module(spec["extra"]["python"]["source"][:-3].replace("/", "."))
    classes = [c for _, c in inspect.getmembers(module, inspect.isclass) if issubclass(c, Tool) and c is not Tool]
    assert len(classes) == 1, classes
    return classes[0]


@pytest.mark.parametrize("tool_file", PROVIDER["tools"])
def test_each_tool_yaml_points_to_one_tool_class(tool_file):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    assert (ROOT / spec["extra"]["python"]["source"]).exists()
    tool_class(spec)


@pytest.mark.parametrize("tool_file", [f for f in PROVIDER["tools"] if "/google_calendar_" in f])
def test_new_tools_emit_every_declared_output(tool_file, http):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    result = run(make_tool(tool_class(spec), {}))
    assert set(result.vars) == set(spec["output_schema"]["properties"]) and result.vars["success"] is False


def test_manifest_and_endpoint():
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0" and manifest["plugins"]["endpoints"] == ["group/google_calendar_signin.yaml"]
    group = yaml.safe_load((ROOT / "group" / "google_calendar_signin.yaml").read_text(encoding="utf-8"))
    assert yaml.safe_load((ROOT / group["endpoints"][0]).read_text(encoding="utf-8"))["path"] == "/google_calendar/callback"
    assert "oauth_schema" in PROVIDER and set(PROVIDER["credentials_for_provider"]) == {"auth_mode", "client_id", "client_secret", "redirect_uri"}


def test_provider_validation(http):
    provider = GoogleCalendarProvider.__new__(GoogleCalendarProvider)
    provider._validate_credentials(PER_USER)
    assert http.calls == []
    for change, message in [({"client_secret": ""}, "Client Secret"), ({"redirect_uri": "http://dify.example.com/e/x/google_calendar/callback"}, "https"),
                            ({"redirect_uri": "https://dify.example.com/e/x/jira/callback"}, "/google_calendar/callback")]:
        with pytest.raises(ToolProviderCredentialValidationError, match=message):
            provider._validate_credentials({**PER_USER, **change})
    http.on("GET", "/calendars/primary", {"id": "primary"})
    provider._validate_credentials(OAUTH)


def test_original_tools_send_log_messages_with_metadata(http):
    """Newer Dify rejects a log message whose metadata is None (the SDK default)."""
    import pathlib
    import re

    for name in ("create_event", "list_calendars", "list_events", "search_events"):
        source = pathlib.Path(ROOT / "tools" / f"{name}.py").read_text(encoding="utf-8")
        calls = re.findall(r"self\.create_log_message\((.*?)\n\s*\)", source, re.S)
        assert calls and all("metadata=" in c for c in calls), name


def test_original_tools_encode_calendar_ids(http):
    from tools.list_events import ListEventsTool

    http.on("GET", "/events", {"items": []})
    run(make_tool(ListEventsTool, OAUTH), {"calendar_id": "en.usa#holiday@group.v.calendar.google.com"})
    assert http.calls[0].url == f"{API}/calendars/en.usa%23holiday%40group.v.calendar.google.com/events"
