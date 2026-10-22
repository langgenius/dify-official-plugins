import json
from types import SimpleNamespace

import pytest

import tools.get_schedule as schedule_module
import tools.graph_client as graph_module
import tools.list_calendar_groups as groups_module
import tools.list_calendars as calendars_module
import tools.list_events as events_module
import tools.search_events as search_module
from provider.outlook import OutlookProvider
from tools.get_schedule import GetScheduleTool
from tools.list_calendar_groups import ListCalendarGroupsTool
from tools.list_calendars import ListCalendarsTool
from tools.list_events import ListEventsTool
from tools.search_events import SearchEventsTool

OAUTH = {"access_token": "user", "refresh_token": "r"}
ME = "https://graph.microsoft.com/v1.0/me"
GROUP_CALENDARS = {
    "value": [
        {"id": "cal/A+1=", "name": "CEO", "owner": {"name": "Kim CEO", "address": "ceo@contoso.com"}},
        {"id": "calB", "name": "CFO", "owner": {"name": "Lee CFO", "address": "CFO@contoso.com"}},
    ]
}


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        return self._payload


class Recorder:
    """Fake for requests.get / requests.post that answers by URL suffix."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, headers=None, params=None, json=None, data=None, timeout=None):
        self.calls.append(SimpleNamespace(url=url, headers=headers or {}, params=params, json=json))
        for suffix, response in self.routes:
            if url.endswith(suffix):
                return response(self.calls[-1]) if callable(response) else response
        raise AssertionError(f"unexpected {url}")


def run(cls, params, credentials=OAUTH):
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=credentials)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    return list(tool._invoke(params))


def test_scope_includes_shared_calendars():
    assert "Calendars.Read.Shared" in OutlookProvider._SCOPE.split()


def test_list_calendar_groups(monkeypatch):
    fake = Recorder([("/calendarGroups", FakeResponse({"value": [{"id": "g1", "name": "People's calendars", "classId": "x"}]}))])
    monkeypatch.setattr(groups_module.requests, "get", fake)
    out = run(ListCalendarGroupsTool, {})
    assert fake.calls[0].url == f"{ME}/calendarGroups"
    assert out[1] == ("json", {"calendar_groups": [{"id": "g1", "name": "People's calendars"}]})


def test_list_calendars_in_a_group_shows_owners(monkeypatch):
    fake = Recorder([("/calendars", FakeResponse(GROUP_CALENDARS))])
    monkeypatch.setattr(calendars_module.requests, "get", fake)
    out = run(ListCalendarsTool, {"calendar_group_id": "g/1"})
    assert fake.calls[0].url == f"{ME}/calendarGroups/g%2F1/calendars"
    assert "owner: Kim CEO <ceo@contoso.com>" in out[0][1]


def test_list_events_with_calendar_id_is_url_encoded(monkeypatch):
    fake = Recorder([("/events", FakeResponse({"value": []}))])
    monkeypatch.setattr(events_module.requests, "get", fake)
    run(ListEventsTool, {"calendar_id": "cal/A+1="})
    assert fake.calls[0].url == f"{ME}/calendars/cal%2FA%2B1%3D/events"


def test_list_events_merges_a_group_and_survives_one_unreadable_calendar(monkeypatch):
    fake = Recorder([
        ("/calendarGroups/g1/calendars", FakeResponse(GROUP_CALENDARS)),
        ("/calendars/cal%2FA%2B1%3D/events", FakeResponse({"value": [{"id": "e1", "subject": "Board", "start": {"dateTime": "2026-12-01T09:00:00"}, "end": {"dateTime": "2026-12-01T10:00:00"}}]})),
        ("/calendars/calB/events", FakeResponse({"error": {"code": "ErrorAccessDenied", "message": "Access is denied."}}, 403)),
    ])
    monkeypatch.setattr(graph_module.requests, "get", fake)
    monkeypatch.setattr(events_module.requests, "get", fake)
    out = run(ListEventsTool, {"calendar_group_id": "g1"})
    data = out[1][1]
    assert [e["id"] for e in data["value"]] == ["e1"]
    assert data["value"][0]["calendar"]["owner_address"] == "ceo@contoso.com"
    assert data["errors"][0]["calendar"]["name"] == "CFO"
    assert "Kim CEO" in out[0][1] and "1 calendar(s) could not be read" in out[0][1]


def test_search_events_over_a_group_sorts_by_start(monkeypatch):
    def view(events):
        return FakeResponse({"value": events})

    fake = Recorder([
        ("/calendarGroups/g1/calendars", FakeResponse(GROUP_CALENDARS)),
        ("/calendars/cal%2FA%2B1%3D/calendarView", view([{"id": "late", "subject": "x", "start": {"dateTime": "2026-12-01T15:00:00"}, "end": {"dateTime": "2026-12-01T16:00:00"}}])),
        ("/calendars/calB/calendarView", view([{"id": "early", "subject": "y", "start": {"dateTime": "2026-12-01T08:00:00"}, "end": {"dateTime": "2026-12-01T09:00:00"}}])),
    ])
    monkeypatch.setattr(graph_module.requests, "get", fake)
    monkeypatch.setattr(search_module.requests, "get", fake)
    out = run(SearchEventsTool, {"calendar_group_id": "g1", "start_date": "2026-12-01", "end_date": "2026-12-01"})
    events = out[1][1]["events"]
    assert [e["id"] for e in events] == ["early", "late"]
    assert events[0]["calendar"]["owner_name"] == "Lee CFO"


def test_search_events_single_calendar_error_is_reported(monkeypatch):
    fake = Recorder([("/calendarView", FakeResponse({"error": {"code": "ErrorItemNotFound", "message": "nope"}}, 404))])
    monkeypatch.setattr(search_module.requests, "get", fake)
    out = run(SearchEventsTool, {"calendar_id": "x", "start_date": "2026-12-01"})
    assert out == [("text", out[0][1])] and out[0][1].startswith("API error 404: ErrorItemNotFound: nope")


def _schedule_answer(call):
    return FakeResponse({"value": [
        {"scheduleId": s, "availabilityView": "0220", "scheduleItems": [
            {"status": "busy", "subject": "Board", "start": {"dateTime": "2026-12-01T10:00:00.0000000"}, "end": {"dateTime": "2026-12-01T11:00:00.0000000"}},
        ]} for s in call.json["schedules"]
    ]})


def test_get_schedule_uses_group_owners_dedupes_and_sets_time_zone(monkeypatch):
    fake_get = Recorder([("/calendarGroups/g1/calendars", FakeResponse(GROUP_CALENDARS))])
    fake_post = Recorder([("/calendar/getSchedule", _schedule_answer)])
    monkeypatch.setattr(graph_module.requests, "get", fake_get)
    monkeypatch.setattr(schedule_module.requests, "post", fake_post)
    out = run(GetScheduleTool, {
        "emails": "cfo@contoso.com, pa@contoso.com",
        "calendar_group_id": "g1",
        "start_datetime": "2026-12-01T09:00:00",
        "end_datetime": "2026-12-01",
        "time_zone": "Asia/Seoul",
        "interval_minutes": 60,
    })
    call = fake_post.calls[0]
    assert call.url == f"{ME}/calendar/getSchedule"
    assert call.json["schedules"] == ["cfo@contoso.com", "pa@contoso.com", "ceo@contoso.com"]
    assert call.json["startTime"] == {"dateTime": "2026-12-01T09:00:00", "timeZone": "Asia/Seoul"}
    assert call.json["endTime"] == {"dateTime": "2026-12-01T23:59:59", "timeZone": "Asia/Seoul"}
    assert call.json["availabilityViewInterval"] == 60
    assert call.headers["Prefer"] == 'outlook.timezone="Asia/Seoul"'
    sched = out[1][1]["schedules"][0]
    assert sched["availability"] == ["free", "busy", "busy", "free"]
    assert sched["busy"][0]["subject"] == "Board"
    assert "12-01 10:00-11:00 busy (Board)" in out[0][1]


def test_get_schedule_converts_offsets_to_utc():
    assert GetScheduleTool._graph_time("2026-12-01T09:00:00+09:00", "Asia/Seoul", False) == {"dateTime": "2026-12-01T00:00:00", "timeZone": "UTC"}


def test_get_schedule_chunks_large_lists(monkeypatch):
    fake_post = Recorder([("/calendar/getSchedule", _schedule_answer)])
    monkeypatch.setattr(schedule_module.requests, "post", fake_post)
    emails = ",".join(f"u{i}@contoso.com" for i in range(45))
    out = run(GetScheduleTool, {"emails": emails, "start_datetime": "2026-12-01", "end_datetime": "2026-12-01"})
    assert [len(c.json["schedules"]) for c in fake_post.calls] == [20, 20, 5]
    assert len(out[1][1]["schedules"]) == 45


def test_get_schedule_service_principal_uses_the_mailbox(monkeypatch):
    # graph_client and get_schedule share the requests module, so one fake answers the token request too.
    fake_post = Recorder([
        ("/oauth2/v2.0/token", FakeResponse({"access_token": "app", "expires_in": 3599})),
        ("/calendar/getSchedule", _schedule_answer),
    ])
    monkeypatch.setattr(schedule_module.requests, "post", fake_post)
    sp = {"tenant_id": "contoso.onmicrosoft.com", "client_id": "id", "client_secret": "s", "mailbox": "pa@contoso.com"}
    run(GetScheduleTool, {"emails": "ceo@contoso.com", "start_datetime": "2026-12-01", "end_datetime": "2026-12-01"}, sp)
    assert fake_post.calls[-1].url == "https://graph.microsoft.com/v1.0/users/pa@contoso.com/calendar/getSchedule"
    assert fake_post.calls[-1].headers["Authorization"] == "Bearer app"


@pytest.mark.parametrize(
    "params, message",
    [
        ({"emails": "a@b.com"}, "start_datetime and end_datetime are required."),
        ({"emails": "a@b.com", "start_datetime": "tomorrow", "end_datetime": "x"}, "must be ISO 8601"),
        ({"emails": "a@b.com", "start_datetime": "2026-12-01", "end_datetime": "2026-12-01", "interval_minutes": 1}, "between 5 and 1440"),
        ({"start_datetime": "2026-12-01", "end_datetime": "2026-12-01"}, "Provide emails"),
    ],
)
def test_get_schedule_validates_input(monkeypatch, params, message):
    monkeypatch.setattr(schedule_module.requests, "post", lambda *a, **k: pytest.fail("must not call Graph"))
    out = run(GetScheduleTool, params)
    assert message in out[0][1]
