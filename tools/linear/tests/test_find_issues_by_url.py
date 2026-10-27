from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.linear_find_issues_by_url import (  # noqa: E402
    ATTACHMENTS_CONTAINING_URL_QUERY,
    ATTACHMENTS_FOR_URL_QUERY,
    LinearFindIssuesByUrlTool,
)

TICKET_URL = "https://acme.zendesk.com/agent/tickets/123"


def _attachment(attachment_id: str, url: str, issue_id: str = "issue-1") -> dict:
    return {
        "id": attachment_id,
        "title": "Zendesk #123",
        "url": url,
        "sourceType": "zendesk",
        "issue": {
            "id": issue_id,
            "identifier": "ENG-1",
            "title": "Login broken",
            "state": {"id": "s1", "name": "In Progress", "type": "started"},
            "labels": {"nodes": [{"id": "l1", "name": "bug"}]},
        },
    }


def _invoke(parameters: dict, responses: list[dict]) -> tuple[list, mock.MagicMock]:
    tool = LinearFindIssuesByUrlTool.__new__(LinearFindIssuesByUrlTool)
    tool.runtime = SimpleNamespace(credentials={"linear_api_key": "lin_api_x"})
    tool.create_json_message = lambda data: ("json", data)
    tool.create_text_message = lambda text: ("text", text)
    with mock.patch("tools.linear_find_issues_by_url.Linear") as linear_cls:
        linear_cls.return_value.query_graphql.side_effect = responses
        messages = list(tool._invoke(parameters))
    return messages, linear_cls.return_value.query_graphql


def test_exact_match_groups_attachments_by_issue() -> None:
    nodes = [_attachment("a1", TICKET_URL), _attachment("a2", TICKET_URL)]
    messages, query = _invoke({"url": TICKET_URL}, [{"data": {"attachmentsForURL": {"nodes": nodes}}}])

    assert query.call_args.args[0] == ATTACHMENTS_FOR_URL_QUERY
    assert query.call_args.kwargs["variables"] == {"url": TICKET_URL, "first": 20}
    kind, data = messages[0]
    assert kind == "json"
    assert data["count"] == 1
    issue = data["issues"][0]
    assert issue["identifier"] == "ENG-1"
    assert issue["labels"] == [{"id": "l1", "name": "bug"}]
    assert [a["id"] for a in issue["attachments"]] == ["a1", "a2"]
    assert "issue" not in issue["attachments"][0]


def test_exact_match_retries_without_trailing_slash() -> None:
    empty = {"data": {"attachmentsForURL": {"nodes": []}}}
    found = {"data": {"attachmentsForURL": {"nodes": [_attachment("a1", TICKET_URL)]}}}
    messages, query = _invoke({"url": TICKET_URL + "/"}, [empty, found])

    assert [call.kwargs["variables"]["url"] for call in query.call_args_list] == [TICKET_URL + "/", TICKET_URL]
    assert messages[0][1]["count"] == 1


def test_contains_match_rejects_longer_ids() -> None:
    nodes = [
        _attachment("a1", TICKET_URL, "issue-1"),
        _attachment("a2", TICKET_URL + "4", "issue-2"),
        _attachment("a3", TICKET_URL + "?brand=1", "issue-3"),
    ]
    messages, query = _invoke(
        {"url": "acme.zendesk.com/agent/tickets/123", "match_mode": "contains", "limit": 500},
        [{"data": {"attachments": {"nodes": nodes}}}],
    )

    assert query.call_args.args[0] == ATTACHMENTS_CONTAINING_URL_QUERY
    assert query.call_args.kwargs["variables"]["first"] == 100
    assert [issue["id"] for issue in messages[0][1]["issues"]] == ["issue-1", "issue-3"]


def test_requires_url_and_valid_mode() -> None:
    assert _invoke({"url": " "}, [])[0] == [("text", "Error: URL ('url') is required.")]
    assert _invoke({"url": TICKET_URL, "match_mode": "fuzzy"}, [])[0][0][0] == "text"
