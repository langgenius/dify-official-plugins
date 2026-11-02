
import pytest

from tests.fakes import CLOUD_TOKEN, OAUTH, OAUTH_BASE, PER_USER, SERVER_TOKEN, FakeHttp, FakeResponse, make_tool, run
from tools.jira_add_attachment import JiraAddAttachmentTool
from tools.jira_add_comment import JiraAddCommentTool
from tools.jira_client import adf_to_text, resolve_context
from tools.jira_delete_attachment import JiraDeleteAttachmentTool
from tools.jira_delete_comment import JiraDeleteCommentTool
from tools.jira_get_attachment import JiraGetAttachmentTool
from tools.jira_get_changelog import JiraGetChangelogTool
from tools.jira_get_comment import JiraGetCommentTool
from tools.jira_get_user import JiraGetUserTool
from tools.jira_list_attachments import JiraListAttachmentsTool
from tools.jira_list_comments import JiraListCommentsTool
from tools.jira_list_transitions import JiraListTransitionsTool
from tools.jira_notify_issue import JiraNotifyIssueTool
from tools.jira_search_issues import JiraSearchIssuesTool
from tools.jira_search_users import JiraSearchUsersTool
from tools.jira_sign_out import SignOutTool
from tools.jira_transition_issue import JiraTransitionIssueTool
from tools.jira_update_comment import JiraUpdateCommentTool
from tools.jira_update_issue import JiraUpdateIssueTool

ISSUE = {
    "id": "10001",
    "key": "PROJ-1",
    "fields": {
        "summary": "Login fails",
        "status": {"name": "To Do"},
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "Alice"},
        "project": {"key": "PROJ"},
        "labels": ["auth"],
        "description": {"type": "doc", "version": 1, "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Steps"}, {"type": "hardBreak"},
                                             {"type": "text", "text": "1. open"}]}]},
    },
}
TRANSITIONS = {"transitions": [
    {"id": "11", "name": "Start progress", "to": {"name": "In Progress"}},
    {"id": "31", "name": "Resolve", "to": {"name": "Done"}},
]}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def test_contexts_for_each_mode():
    cloud = resolve_context(CLOUD_TOKEN)
    assert cloud.api("myself") == "https://acme.atlassian.net/rest/api/3/myself"
    assert cloud.headers["Authorization"] == "Basic dGVzdA=="
    server = resolve_context(SERVER_TOKEN)
    assert server.api("myself") == "https://jira.example.com/rest/api/2/myself" and not server.cloud
    oauth = resolve_context(OAUTH)
    assert oauth.api("issue/X-1") == f"{OAUTH_BASE}/rest/api/3/issue/X-1"
    assert oauth.agile("board") == f"{OAUTH_BASE}/rest/agile/1.0/board"
    assert oauth.browse("X-1") == "https://acme.atlassian.net/browse/X-1"


def test_search_cloud_follows_next_page_token(http):
    http.on("POST", "/rest/api/3/search/jql",
            {"issues": [ISSUE], "nextPageToken": "p2"},
            {"issues": [{**ISSUE, "key": "PROJ-2"}]})
    result = run(make_tool(JiraSearchIssuesTool, OAUTH), {"jql": "project = PROJ", "limit": 10})
    assert result.vars["success"] and result.vars["count"] == 2
    first = result.vars["issues"][0]
    assert first["key"] == "PROJ-1" and first["status"] == "To Do" and first["assignee"] == "Alice"
    assert first["description"] == "Steps\n1. open"
    assert first["url"] == "https://acme.atlassian.net/browse/PROJ-1"
    calls = [c for c in http.calls if "search" in c.url]
    assert calls[0].json["jql"] == "project = PROJ" and "nextPageToken" not in calls[0].json
    assert calls[1].json["nextPageToken"] == "p2"


def test_search_defaults_to_a_bounded_query_and_server_paging(http):
    http.on("GET", "/rest/api/2/search", {"issues": [ISSUE], "total": 1})
    result = run(make_tool(JiraSearchIssuesTool, SERVER_TOKEN))
    assert result.vars["count"] == 1
    assert http.calls[0].params["jql"].startswith("updated >= -30d")
    assert http.calls[0].url == "https://jira.example.com/rest/api/2/search"


def test_update_issue_sends_only_given_fields(http):
    http.on("PUT", "/issue/PROJ-1", FakeResponse(None, 204))
    result = run(make_tool(JiraUpdateIssueTool, OAUTH), {
        "issue_key": "PROJ-1", "summary": "New", "assignee": "acc-1", "labels": "a, b c", "due_date": "none",
        "description": "**bold**", "custom_fields": '{"customfield_1": 3}', "notify_users": False,
    })
    assert result.vars["success"], result.texts
    fields = http.calls[0].json["fields"]
    assert fields["summary"] == "New"
    assert fields["assignee"] == {"accountId": "acc-1"}
    assert fields["labels"] == ["a", "b_c"]
    assert fields["duedate"] is None
    assert fields["description"]["type"] == "doc"
    assert fields["customfield_1"] == 3
    assert http.calls[0].params == {"notifyUsers": "false"}
    assert set(result.vars["updated_fields"]) == {"summary", "assignee", "labels", "duedate", "description", "customfield_1"}


def test_update_issue_on_server_uses_names_and_plain_text(http):
    http.on("PUT", "/rest/api/2/issue/PROJ-1", FakeResponse(None, 204))
    run(make_tool(JiraUpdateIssueTool, SERVER_TOKEN), {"issue_key": "PROJ-1", "assignee": "bob", "description": "hi"})
    fields = http.calls[0].json["fields"]
    assert fields == {"assignee": {"name": "bob"}, "description": "hi"}


def test_update_issue_needs_a_field_and_valid_json(http):
    result = run(make_tool(JiraUpdateIssueTool, OAUTH), {"issue_key": "PROJ-1"})
    assert not result.vars["success"] and "Nothing to update" in result.vars["error"]
    result = run(make_tool(JiraUpdateIssueTool, OAUTH), {"issue_key": "PROJ-1", "custom_fields": "[1]"})
    assert "JSON object" in result.vars["error"]
    assert http.calls == []


def test_issue_keys_cannot_change_the_path(http):
    http.on("PUT", "/issue/", FakeResponse(None, 204))
    run(make_tool(JiraUpdateIssueTool, OAUTH), {"issue_key": "../../admin?x=1", "summary": "s"})
    assert http.calls[0].url == f"{OAUTH_BASE}/rest/api/3/issue/..%2F..%2Fadmin%3Fx%3D1"


def test_transition_by_status_name_with_comment(http):
    http.on("GET", "/issue/PROJ-1/transitions", TRANSITIONS)
    http.on("POST", "/issue/PROJ-1/transitions", FakeResponse(None, 204))
    result = run(make_tool(JiraTransitionIssueTool, OAUTH), {"issue_key": "PROJ-1", "transition": "done", "comment": "Fixed"})
    assert result.vars["status"] == "Done" and result.vars["transition_id"] == "31"
    body = http.calls[1].json
    assert body["transition"] == {"id": "31"}
    assert body["update"]["comment"][0]["add"]["body"]["type"] == "doc"


def test_transition_unknown_lists_the_options(http):
    http.on("GET", "/issue/PROJ-1/transitions", TRANSITIONS)
    result = run(make_tool(JiraTransitionIssueTool, OAUTH), {"issue_key": "PROJ-1", "transition": "Closed"})
    assert not result.vars["success"]
    assert "In Progress ('Start progress', id 11)" in result.vars["error"]
    assert len(http.calls) == 1


def test_list_transitions(http):
    http.on("GET", "/issue/PROJ-1/transitions", TRANSITIONS)
    result = run(make_tool(JiraListTransitionsTool, OAUTH), {"issue_key": "PROJ-1"})
    assert result.vars["transitions"][1] == {"id": "31", "name": "Resolve", "to_status": "Done"}


def test_changelog_cloud_and_server(http):
    history = {"id": "1", "author": {"displayName": "Bob"}, "created": "2026-01-01",
               "items": [{"field": "status", "fromString": "To Do", "toString": "Done"}]}
    http.on("GET", "/rest/api/3/issue/PROJ-1/changelog", {"values": [history], "isLast": True})
    result = run(make_tool(JiraGetChangelogTool, OAUTH), {"issue_key": "PROJ-1"})
    assert result.vars["histories"][0]["changes"] == [{"field": "status", "from": "To Do", "to": "Done"}]
    http.on("GET", "/rest/api/2/issue/PROJ-1", {"changelog": {"histories": [history]}})
    result = run(make_tool(JiraGetChangelogTool, SERVER_TOKEN), {"issue_key": "PROJ-1"})
    assert result.vars["count"] == 1 and http.calls[-1].params["expand"] == "changelog"


def test_notify(http):
    http.on("POST", "/issue/PROJ-1/notify", FakeResponse(None, 204))
    result = run(make_tool(JiraNotifyIssueTool, OAUTH), {
        "issue_key": "PROJ-1", "subject": "S", "text": "T", "recipients": "assignee, Watchers", "user_ids": "a1"})
    assert result.vars["success"]
    assert http.calls[0].json["to"] == {"reporter": False, "assignee": True, "watchers": True, "voters": False,
                                       "users": [{"accountId": "a1"}]}
    result = run(make_tool(JiraNotifyIssueTool, OAUTH), {"issue_key": "PROJ-1", "subject": "S", "text": "T", "recipients": "boss"})
    assert "Unknown recipients" in result.vars["error"]


def test_comment_crud(http):
    comment = {"id": "500", "author": {"displayName": "Alice"}, "created": "c", "updated": "u",
               "body": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hi"}]}]}}
    http.on("POST", "/issue/PROJ-1/comment", comment)
    http.on("GET", "/issue/PROJ-1/comment/500", comment)
    http.on("PUT", "/issue/PROJ-1/comment/500", comment)
    http.on("DELETE", "/issue/PROJ-1/comment/500", FakeResponse(None, 204))
    http.on("GET", "/issue/PROJ-1/comment", {"comments": [comment], "total": 1})

    added = run(make_tool(JiraAddCommentTool, OAUTH), {"issue_key": "PROJ-1", "comment": "Hi"})
    assert added.vars["comment_id"] == "500" and http.calls[-1].json["body"]["type"] == "doc"
    got = run(make_tool(JiraGetCommentTool, OAUTH), {"issue_key": "PROJ-1", "comment_id": "500"})
    assert got.vars["body"] == "Hi" and got.vars["author"] == "Alice"
    updated = run(make_tool(JiraUpdateCommentTool, OAUTH), {"issue_key": "PROJ-1", "comment_id": "500", "comment": "Bye"})
    assert updated.vars["success"]
    listed = run(make_tool(JiraListCommentsTool, OAUTH), {"issue_key": "PROJ-1", "newest_first": True})
    assert listed.vars["count"] == 1 and http.calls[-1].params["orderBy"] == "-created"
    deleted = run(make_tool(JiraDeleteCommentTool, OAUTH), {"issue_key": "PROJ-1", "comment_id": "500"})
    assert deleted.vars["deleted"] is True


def test_add_attachment_from_text(http):
    http.on("POST", "/issue/PROJ-1/attachments", [{"id": "9", "filename": "notes.txt", "size": 5, "mimeType": "text/plain"}])
    result = run(make_tool(JiraAddAttachmentTool, OAUTH), {"issue_key": "PROJ-1", "file_content": "hello", "file_name": "notes.txt"})
    assert result.vars["attachment_id"] == "9" and result.vars["size"] == 5
    call = http.calls[0]
    assert call.headers["X-Atlassian-Token"] == "no-check"
    assert call.files["file"] == ("notes.txt", b"hello", "text/plain")
    assert "json" not in vars(call)
    result = run(make_tool(JiraAddAttachmentTool, OAUTH), {"issue_key": "PROJ-1", "file_content": "x"})
    assert "file name" in result.vars["error"]


def test_get_attachment_downloads_through_the_api(http):
    http.on("GET", "/rest/api/3/attachment/content/9", FakeResponse(None, 200, content=b"PDFDATA"))
    http.on("GET", "/rest/api/3/attachment/9", {"id": "9", "filename": "a.pdf", "mimeType": "application/pdf", "size": 7,
                                                "content": "https://acme.atlassian.net/rest/api/3/attachment/content/9"})
    result = run(make_tool(JiraGetAttachmentTool, OAUTH), {"attachment_id": "9"})
    assert result.blobs[0][1] == b"PDFDATA"
    assert result.blobs[0][2] == {"mime_type": "application/pdf", "filename": "a.pdf"}
    # The OAuth token is only ever sent to api.atlassian.com.
    assert all(c.url.startswith(OAUTH_BASE) for c in http.calls)


def test_server_attachment_link_only_followed_on_the_jira_host(http):
    http.on("GET", "/rest/api/2/attachment/9", {"id": "9", "filename": "a", "size": 1, "content": "https://evil.example/x"})
    http.on("GET", "/rest/api/2/attachment/content/9", FakeResponse(None, 200, content=b"x"))
    run(make_tool(JiraGetAttachmentTool, SERVER_TOKEN), {"attachment_id": "9"})
    assert not any("evil" in c.url for c in http.calls)


def test_list_and_delete_attachments(http):
    http.on("GET", "/issue/PROJ-1", {"fields": {"attachment": [{"id": "9", "filename": "a.txt", "size": 3}]}})
    http.on("DELETE", "/attachment/9", FakeResponse(None, 204))
    listed = run(make_tool(JiraListAttachmentsTool, OAUTH), {"issue_key": "PROJ-1"})
    assert listed.vars["attachments"][0]["filename"] == "a.txt"
    assert run(make_tool(JiraDeleteAttachmentTool, OAUTH), {"attachment_id": "9"}).vars["deleted"]


def test_users(http):
    http.on("GET", "/user/search", [
        {"accountId": "a1", "displayName": "Alice", "accountType": "atlassian"},
        {"accountId": "bot", "displayName": "Automation", "accountType": "app"},
    ])
    http.on("GET", "/myself", {"accountId": "me", "displayName": "Me", "emailAddress": "me@acme.com",
                               "groups": {"items": [{"name": "jira-users"}]}})
    found = run(make_tool(JiraSearchUsersTool, OAUTH), {"query": "ali"})
    assert [u["account_id"] for u in found.vars["users"]] == ["a1"]
    assert http.calls[0].params["query"] == "ali"
    me = run(make_tool(JiraGetUserTool, OAUTH))
    assert me.vars["account_id"] == "me" and me.json[0]["groups"] == ["jira-users"]
    run(make_tool(JiraSearchUsersTool, SERVER_TOKEN), {"query": "bob"})
    assert http.calls[-1].params["username"] == "bob"


def test_api_errors_become_tool_errors(http):
    http.on("GET", "/issue/PROJ-9/transitions", FakeResponse({"errorMessages": ["Issue does not exist"]}, 404))
    result = run(make_tool(JiraListTransitionsTool, OAUTH), {"issue_key": "PROJ-9"})
    assert not result.vars["success"]
    assert "Jira API error 404: Issue does not exist" in result.vars["error"]


def test_per_user_tool_returns_the_sign_in_link(http):
    result = run(make_tool(JiraSearchIssuesTool, PER_USER), {"jql": "x"})
    assert not result.vars["success"]
    assert "https://auth.atlassian.com/authorize?" in result.texts[0]
    assert http.calls == []


def test_sign_out_tool_modes(http):
    shared = run(make_tool(SignOutTool, OAUTH))
    assert "only applies" in shared.texts[0] and not shared.vars["success"]
    per_user = run(make_tool(SignOutTool, PER_USER))
    assert per_user.vars == {"signed_out": False, "success": True, "error": ""}


def test_adf_to_text_handles_lists_and_mentions():
    doc = {"type": "doc", "content": [
        {"type": "bulletList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}]},
            {"type": "listItem", "content": [{"type": "paragraph", "content": [
                {"type": "mention", "attrs": {"text": "@Bob"}}]}]}]}]}
    assert adf_to_text(doc).split() == ["a", "@Bob"]
    assert adf_to_text("plain") == "plain" and adf_to_text(None) == ""


def test_notify_without_recipients_explains_why(http):
    http.on("POST", "/issue/PROJ-1/notify", FakeResponse({"errorMessages": ["No recipients were defined for notification."]}, 400))
    result = run(make_tool(JiraNotifyIssueTool, OAUTH), {"issue_key": "PROJ-1", "subject": "S", "text": "T", "recipients": "assignee"})
    assert not result.vars["success"]
    assert "never emails the sender" in result.vars["error"]
