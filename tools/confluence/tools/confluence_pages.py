"""Page reads and writes shared by several tools (kept out of the tool files: Dify loads one Tool class per file)."""

from typing import Any

from tools.confluence_client import ConfluenceContext, confluence_request, page_dict, segment


def get_page(ctx: ConfluenceContext, page_id: str) -> dict[str, Any]:
    """A page with its storage body, version and space."""
    if ctx.cloud:
        page = confluence_request(ctx, "GET", ctx.v2(f"pages/{segment(page_id)}"), params={"body-format": "storage"}).json()
    else:
        page = confluence_request(
            ctx, "GET", ctx.v1(f"content/{segment(page_id)}"), params={"expand": "body.storage,version,space,ancestors"}
        ).json()
        ancestors = page.get("ancestors") or []
        if ancestors:
            page["parentId"] = ancestors[-1].get("id")
    return page_dict(ctx, page, with_body=True)


def put_page(ctx: ConfluenceContext, page: dict[str, Any], title: str, storage: str, message: str = "") -> dict[str, Any]:
    """Save a new version of a page (Confluence needs the next version number)."""
    version = {"number": page["version"] + 1}
    if message:
        version["message"] = message
    if ctx.cloud:
        body = {"id": page["id"], "status": "current", "title": title,
                "body": {"representation": "storage", "value": storage}, "version": version}
        saved = confluence_request(ctx, "PUT", ctx.v2(f"pages/{segment(page['id'])}"), json_body=body).json()
    else:
        body = {"id": page["id"], "type": "page", "title": title,
                "body": {"storage": {"value": storage, "representation": "storage"}}, "version": version}
        saved = confluence_request(ctx, "PUT", ctx.v1(f"content/{segment(page['id'])}"), json_body=body).json()
    return page_dict(ctx, saved)
