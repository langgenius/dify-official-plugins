import pytest

from tests.fakes import CLOUD_TOKEN, OAUTH, OAUTH_BASE, PER_USER, SERVER_TOKEN, FakeHttp, FakeResponse, make_tool, run
from tools.confluence_add_comment import ConfluenceAddCommentTool
from tools.confluence_add_labels import ConfluenceAddLabelsTool
from tools.confluence_client import resolve_context, storage_to_text, to_storage
from tools.confluence_delete_attachment import ConfluenceDeleteAttachmentTool
from tools.confluence_delete_comment import ConfluenceDeleteCommentTool
from tools.confluence_get_attachment import ConfluenceGetAttachmentTool
from tools.confluence_get_labels import ConfluenceGetLabelsTool
from tools.confluence_list_attachments import ConfluenceListAttachmentsTool
from tools.confluence_list_child_pages import ConfluenceListChildPagesTool
from tools.confluence_list_comments import ConfluenceListCommentsTool
from tools.confluence_read_page import ConfluenceReadPageTool
from tools.confluence_remove_label import ConfluenceRemoveLabelTool
from tools.confluence_search import ConfluenceSearchTool, build_cql
from tools.confluence_sign_out import SignOutTool
from tools.confluence_update_page import ConfluenceUpdatePageTool
from tools.confluence_upload_attachment import ConfluenceUploadAttachmentTool

PAGE = {"id": "100", "title": "Runbook", "status": "current", "spaceId": "9", "parentId": "50",
        "version": {"number": 3, "createdAt": "2026-01-01"},
        "body": {"storage": {"value": "<h1>Steps</h1><p>Open the <strong>door</strong>.</p><ul><li>a</li><li>b</li></ul>"}},
        "_links": {"webui": "/spaces/DEV/pages/100/Runbook"}}
SERVER_PAGE = {"id": "100", "title": "Runbook", "type": "page", "version": {"number": 3},
               "space": {"id": 9, "key": "DEV"}, "ancestors": [{"id": "1"}, {"id": "50"}],
               "body": {"storage": {"value": "<p>Hi</p>"}}, "_links": {"webui": "/display/DEV/Runbook"}}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def test_contexts_for_each_mode():
    cloud = resolve_context(CLOUD_TOKEN)
    assert cloud.cloud and cloud.base_url == "https://acme.atlassian.net"
    assert cloud.v2("pages/1") == "https://acme.atlassian.net/wiki/api/v2/pages/1"
    assert cloud.v1("search") == "https://acme.atlassian.net/wiki/rest/api/search"
    assert cloud.headers["Authorization"].startswith("Basic ")
    server = resolve_context(SERVER_TOKEN)
    assert not server.cloud and server.v1("content/1") == "https://wiki.example.com/confluence/rest/api/content/1"
    assert server.headers["Authorization"] == "Bearer pat"
    assert server.web("/display/DEV/X") == "https://wiki.example.com/confluence/display/DEV/X"
    oauth = resolve_context(OAUTH)
    assert oauth.v2("spaces") == f"{OAUTH_BASE}/wiki/api/v2/spaces"
    assert oauth.web("/spaces/DEV/pages/1") == "https://acme.atlassian.net/wiki/spaces/DEV/pages/1"


def test_markdown_and_text_conversion():
    storage = to_storage("# Title\n\n**bold** and a [link](https://x.y)\n\n- a\n- b", "markdown")
    assert "<h1>Title</h1>" in storage and "<strong>bold</strong>" in storage and "<li>a</li>" in storage
    assert to_storage("<p>raw</p>", "storage") == "<p>raw</p>"
    assert storage_to_text(PAGE["body"]["storage"]["value"]).splitlines() == ["Steps", "", "Open the door.", "", "- a", "- b"]
    # Markdown output has newlines between list items; they must not become blank lines.
    assert storage_to_text(to_storage("- a\n- b", "markdown")) == "- a\n- b"


def test_build_cql():
    assert build_cql({"text": 'say "hi"', "space_key": "DEV"}) == 'text ~ "say \\"hi\\"" AND space = "DEV" AND type = "page" ORDER BY lastmodified DESC'
    assert build_cql({"label": "q3", "content_type": "any"}) == 'label = "q3" ORDER BY lastmodified DESC'
    assert build_cql({"cql": "creator = currentUser()", "text": "ignored"}) == "creator = currentUser()"
    with pytest.raises(Exception, match="Give a CQL query"):
        build_cql({"content_type": "page"})


def test_search_follows_cursor(http):
    hit = {"content": {"id": "100", "type": "page", "title": "Runbook", "_links": {"webui": "/spaces/DEV/pages/100"}},
           "excerpt": "open the @@@hl@@@door@@@endhl@@@", "url": "/spaces/DEV/pages/100", "resultGlobalContainer": {"title": "Dev"}}
    http.on("GET", "/wiki/rest/api/search",
            {"results": [hit], "_links": {"next": "/rest/api/search?next=true&cursor=_t_W1%3D%3D&limit=25&start=1&cql=x"}},
            {"results": [{**hit, "content": {**hit["content"], "id": "101"}}], "_links": {}})
    result = run(make_tool(ConfluenceSearchTool, OAUTH), {"text": "door"})
    assert result.vars["count"] == 2
    assert result.vars["results"][0] == {"id": "100", "type": "page", "title": "Runbook", "space": "Dev",
                                         "excerpt": "open the door", "last_modified": "",
                                         "url": "https://acme.atlassian.net/wiki/spaces/DEV/pages/100"}
    # The cursor is passed decoded (requests encodes it once) together with next=true and start.
    assert http.calls[1].params["cursor"] == "_t_W1=="
    assert http.calls[1].params["next"] == "true" and http.calls[1].params["start"] == "1"
    assert all(c.url.startswith(OAUTH_BASE) for c in http.calls)


def test_read_page_cloud_and_server(http):
    http.on("GET", "/wiki/api/v2/pages/100", PAGE)
    result = run(make_tool(ConfluenceReadPageTool, OAUTH), {"page_id": "100"})
    assert result.vars["title"] == "Runbook" and result.vars["version"] == 3
    assert "Open the door." in result.vars["body_text"]
    assert result.vars["url"] == "https://acme.atlassian.net/wiki/spaces/DEV/pages/100/Runbook"
    assert http.calls[0].params == {"body-format": "storage"}

    http.on("GET", "/confluence/rest/api/content/100", SERVER_PAGE)
    result = run(make_tool(ConfluenceReadPageTool, SERVER_TOKEN), {"page_id": "100"})
    assert result.vars["body_text"] == "Hi" and result.json[0]["parent_id"] == "50" and result.json[0]["space_key"] == "DEV"


def test_update_page_append_bumps_version(http):
    http.on("GET", "/wiki/api/v2/pages/100", PAGE)
    http.on("PUT", "/wiki/api/v2/pages/100", {**PAGE, "version": {"number": 4}})
    result = run(make_tool(ConfluenceUpdatePageTool, OAUTH), {"page_id": "100", "body": "More **text**", "mode": "append"})
    assert result.vars["version"] == 4, result.texts
    body = http.calls[1].json
    assert body["version"] == {"number": 4} and body["title"] == "Runbook" and body["status"] == "current"
    assert body["body"]["value"].startswith(PAGE["body"]["storage"]["value"])
    assert body["body"]["value"].endswith("<p>More <strong>text</strong></p>")


def test_update_page_server_rename_only(http):
    http.on("GET", "/rest/api/content/100", SERVER_PAGE)
    http.on("PUT", "/rest/api/content/100", {**SERVER_PAGE, "title": "New", "version": {"number": 4}})
    result = run(make_tool(ConfluenceUpdatePageTool, SERVER_TOKEN), {"page_id": "100", "title": "New", "version_message": "why"})
    put = http.calls[1].json
    assert put["type"] == "page" and put["title"] == "New" and put["body"]["storage"]["value"] == "<p>Hi</p>"
    assert put["version"] == {"number": 4, "message": "why"}
    assert "Renamed" in result.texts[-1]


def test_update_page_validates(http):
    result = run(make_tool(ConfluenceUpdatePageTool, OAUTH), {"page_id": "100"})
    assert "Nothing to update" in result.vars["error"]
    result = run(make_tool(ConfluenceUpdatePageTool, OAUTH), {"page_id": "100", "body": "x", "mode": "merge"})
    assert "mode must be" in result.vars["error"]
    assert http.calls == []


def test_ids_cannot_change_the_path(http):
    run(make_tool(ConfluenceReadPageTool, OAUTH), {"page_id": "../../admin?x=1"})
    assert http.calls[0].url == f"{OAUTH_BASE}/wiki/api/v2/pages/..%2F..%2Fadmin%3Fx%3D1"


def test_child_pages_cloud_cursor_and_server(http):
    http.on("GET", "/pages/100/children",
            {"results": [{"id": "101", "title": "A"}], "_links": {"next": "/wiki/api/v2/pages/100/children?cursor=c2%3D&limit=50"}},
            {"results": [{"id": "102", "title": "B"}], "_links": {}})
    result = run(make_tool(ConfluenceListChildPagesTool, OAUTH), {"page_id": "100"})
    assert [p["id"] for p in result.vars["pages"]] == ["101", "102"] and http.calls[1].params["cursor"] == "c2="
    http.on("GET", "/content/100/child/page", {"results": [{"id": "7", "title": "S"}]})
    assert run(make_tool(ConfluenceListChildPagesTool, SERVER_TOKEN), {"page_id": "100"}).vars["count"] == 1


def test_comments(http):
    comment = {"id": "500", "body": {"storage": {"value": "<p>Nice</p>"}}, "version": {"authorId": "acc", "createdAt": "t"}}
    http.on("POST", "/wiki/api/v2/footer-comments", comment)
    http.on("GET", "/pages/100/footer-comments", {"results": [comment], "_links": {}})
    http.on("DELETE", "/wiki/api/v2/footer-comments/500", FakeResponse(None, 204))
    added = run(make_tool(ConfluenceAddCommentTool, OAUTH), {"page_id": "100", "comment": "**Nice**"})
    assert added.vars["comment_id"] == "500"
    assert http.calls[0].json == {"pageId": "100", "body": {"representation": "storage", "value": "<p><strong>Nice</strong></p>"}}
    listed = run(make_tool(ConfluenceListCommentsTool, OAUTH), {"page_id": "100"})
    assert listed.vars["comments"][0] == {"id": "500", "body": "Nice", "author_id": "acc", "created": "t"}
    assert run(make_tool(ConfluenceDeleteCommentTool, OAUTH), {"comment_id": "500"}).vars["deleted"]


def test_server_comment_is_content(http):
    http.on("POST", "/rest/api/content", {"id": "9"})
    run(make_tool(ConfluenceAddCommentTool, SERVER_TOKEN), {"page_id": "100", "comment": "hi"})
    body = http.calls[0].json
    assert body["type"] == "comment" and body["container"] == {"id": "100", "type": "page"}


def test_labels(http):
    http.on("GET", "/pages/100/labels", {"results": [{"name": "ops"}]})
    http.on("POST", "/wiki/rest/api/content/100/label", {"results": [{"name": "ops"}, {"name": "release-notes"}]})
    http.on("DELETE", "/wiki/rest/api/content/100/label", FakeResponse(None, 204))
    assert run(make_tool(ConfluenceGetLabelsTool, OAUTH), {"page_id": "100"}).vars["labels"] == ["ops"]
    added = run(make_tool(ConfluenceAddLabelsTool, OAUTH), {"page_id": "100", "labels": "Release Notes, "})
    assert http.calls[-1].json == [{"prefix": "global", "name": "release-notes"}]
    assert added.vars["labels"] == ["ops", "release-notes"]
    run(make_tool(ConfluenceRemoveLabelTool, OAUTH), {"page_id": "100", "label": "a/b"})
    assert http.calls[-1].params == {"name": "a/b"}


def test_attachments(http):
    http.on("GET", "/pages/100/attachments", {"results": [{"id": "att1", "title": "a.txt", "mediaType": "text/plain", "fileSize": 3, "pageId": "100"}]})
    http.on("POST", "/wiki/rest/api/content/100/child/attachment",
            {"results": [{"id": "att2", "title": "notes.txt", "extensions": {"mediaType": "text/plain", "fileSize": 5}}]})
    http.on("GET", "/wiki/api/v2/attachments/att1", {"id": "att1", "title": "a.txt", "mediaType": "text/plain", "fileSize": 3, "pageId": "100"})
    http.on("GET", "/wiki/rest/api/content/100/child/attachment/att1/download", FakeResponse(None, 200, content=b"abc"))
    http.on("DELETE", "/wiki/api/v2/attachments/att1", FakeResponse(None, 204))

    assert run(make_tool(ConfluenceListAttachmentsTool, OAUTH), {"page_id": "100"}).vars["count"] == 1
    up = run(make_tool(ConfluenceUploadAttachmentTool, OAUTH), {"page_id": "100", "file_content": "hello", "file_name": "notes.txt", "comment": "v1"})
    assert up.vars["attachment_id"] == "att2" and up.vars["size"] == 5
    call = http.calls[-1]
    assert call.headers["X-Atlassian-Token"] == "no-check"
    assert call.files["file"] == ("notes.txt", b"hello", "text/plain") and call.files["comment"] == (None, "v1")
    got = run(make_tool(ConfluenceGetAttachmentTool, OAUTH), {"attachment_id": "att1"})
    assert got.blobs[0][1] == b"abc" and got.blobs[0][2] == {"mime_type": "text/plain", "filename": "a.txt"}
    assert run(make_tool(ConfluenceDeleteAttachmentTool, OAUTH), {"attachment_id": "att1"}).vars["deleted"]
    assert all(c.url.startswith(OAUTH_BASE) for c in http.calls)


def test_server_attachment_download_stays_on_host(http):
    http.on("GET", "/rest/api/content/att1", {"id": "att1", "title": "a", "extensions": {"fileSize": 1},
                                              "_links": {"download": "//evil.example/x"}})
    result = run(make_tool(ConfluenceGetAttachmentTool, SERVER_TOKEN), {"attachment_id": "att1"})
    assert "no download link" in result.vars["error"]
    assert not any("evil" in c.url for c in http.calls)
    http.routes.clear()
    http.on("GET", "/rest/api/content/att1", {"id": "att1", "title": "a", "extensions": {"fileSize": 1},
                                              "_links": {"download": "/download/attachments/100/a"}})
    http.on("GET", "/download/attachments/100/a", FakeResponse(None, 200, content=b"x"))
    result = run(make_tool(ConfluenceGetAttachmentTool, SERVER_TOKEN), {"attachment_id": "att1"})
    assert result.blobs[0][1] == b"x"
    assert http.calls[-1].url == "https://wiki.example.com/confluence/download/attachments/100/a"


def test_api_errors_become_tool_errors(http):
    http.on("GET", "/wiki/api/v2/pages/9", FakeResponse({"errors": [{"title": "Page not found"}]}, 404))
    result = run(make_tool(ConfluenceReadPageTool, OAUTH), {"page_id": "9"})
    assert "Confluence API error 404: Page not found" in result.vars["error"]


def test_per_user_tool_returns_the_sign_in_link(http):
    result = run(make_tool(ConfluenceSearchTool, PER_USER), {"text": "x"})
    assert "https://auth.atlassian.com/authorize?" in result.texts[0] and http.calls == []


def test_sign_out_tool_modes(http):
    assert "only applies" in run(make_tool(SignOutTool, OAUTH)).texts[0]
    assert run(make_tool(SignOutTool, PER_USER)).vars == {"signed_out": False, "success": True, "error": ""}
