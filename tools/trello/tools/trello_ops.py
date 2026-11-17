"""
The operations behind the ``trello_*`` tools. Each takes the Trello context and the tool
parameters and returns (output variables, JSON message, text message); ``run`` handles
credentials and errors, so every tool file is a thin wrapper (Dify loads one Tool class per file).
"""

from typing import Any, Callable, Mapping
from urllib.parse import quote, urlparse

from tools.trello_client import (
    TrelloAuthError,
    TrelloContext,
    attachment_dict,
    card_dict,
    checklist_dict,
    json_of,
    label_dict,
    member_dict,
    require,
    resolve_context,
    segment,
    split_ids,
    trello_request,
)

Result = tuple[dict[str, Any], Any, str]
CARD_FIELDS = "name,desc,idList,idBoard,due,dueComplete,closed,labels,idMembers,shortUrl"
COLORS = ("green", "yellow", "orange", "red", "purple", "blue", "sky", "lime", "pink", "black")
# Larger files are described but not downloaded into the conversation.
MAX_DOWNLOAD = 50 * 1024 * 1024


def run(tool: Any, params: Mapping[str, Any], op: Callable[[TrelloContext, Mapping[str, Any]], Result]):
    try:
        ctx = resolve_context(tool.runtime.credentials, tool)
        out, data, text = op(ctx, params)
    except TrelloAuthError as e:
        yield tool.create_text_message(str(e))
        return
    blob = out.pop("_blob", None)
    tool._out.update(out, success=True)
    yield tool.create_json_message(data)
    if blob is not None:
        yield tool.create_blob_message(blob[0], meta=blob[1])
    yield tool.create_text_message(text)


def _flag(value: Any) -> bool | None:
    """A boolean parameter that may be absent (None) or arrive as a string."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


# ── cards and search ─────────────────────────────────────────────────


def get_card(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (card_id,) = require(p, "card_id")
    card = json_of(trello_request(ctx, "GET", f"cards/{segment(card_id)}", params={
        "fields": CARD_FIELDS, "checklists": "all", "members": "true", "member_fields": "username,fullName",
        "list": "true", "attachments": "true", "attachment_fields": "name,url,bytes,mimeType,isUpload,date",
    }))
    result = card_dict(card)
    result["list_name"] = (card.get("list") or {}).get("name", "")
    result["members"] = [member_dict(m) for m in card.get("members") or []]
    result["checklists"] = [checklist_dict(c) for c in card.get("checklists") or []]
    result["attachments"] = [attachment_dict(a) for a in card.get("attachments") or []]
    out = {"card": result, "name": result["name"], "desc": result["desc"], "list_name": result["list_name"], "url": result["url"]}
    progress = ", ".join(f"{c['name']} {c['completed']}/{c['total']}" for c in result["checklists"])
    text = (f"{result['name']} (in '{result['list_name']}')\n{result['url']}\n"
            + (f"Due: {result['due']}{' (done)' if result['due_complete'] else ''}\n" if result["due"] else "")
            + (f"Labels: {', '.join(result['labels'])}\n" if result["labels"] else "")
            + (f"Checklists: {progress}\n" if progress else "")
            + (f"\n{result['desc']}" if result["desc"] else ""))
    return out, result, text.strip()


def search(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (query,) = require(p, "query")
    limit = max(1, min(int(p.get("limit") or 20), 100))
    params: dict[str, Any] = {"query": query, "modelTypes": "cards,boards", "cards_limit": limit, "boards_limit": 10,
                              "card_fields": CARD_FIELDS, "board_fields": "name,url,closed", "partial": "true"}
    if p.get("board_id"):
        params["idBoards"] = str(p["board_id"]).strip()
    body = json_of(trello_request(ctx, "GET", "search", params=params))
    cards = [card_dict(c) for c in body.get("cards") or []]
    boards = [{"id": b.get("id", ""), "name": b.get("name", ""), "url": b.get("url", ""), "closed": bool(b.get("closed"))}
              for b in body.get("boards") or []]
    text = (f"Found {len(cards)} card(s) and {len(boards)} board(s)."
            + "".join(f"\n- card: {c['name']} (id {c['id']})" for c in cards[:15])
            + "".join(f"\n- board: {b['name']} (id {b['id']})" for b in boards[:5]))
    return {"cards": cards, "boards": boards, "count": len(cards)}, {"cards": cards, "boards": boards}, text


# ── comments ─────────────────────────────────────────────────────────


def _comment(action: Mapping[str, Any]) -> dict[str, Any]:
    return {"id": action.get("id", ""), "text": (action.get("data") or {}).get("text", ""),
            "author": (action.get("memberCreator") or {}).get("fullName", ""), "date": action.get("date", "")}


def list_comments(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (card_id,) = require(p, "card_id")
    limit = max(1, min(int(p.get("limit") or 50), 1000))
    actions = json_of(trello_request(ctx, "GET", f"cards/{segment(card_id)}/actions",
                                     params={"filter": "commentCard", "limit": limit}))
    comments = [_comment(a) for a in actions]
    return ({"comments": comments, "count": len(comments)}, {"card_id": card_id, "comments": comments},
            f"The card has {len(comments)} comment(s)." + "".join(f"\n- {c['author']}: {c['text']}" for c in comments[:10]))


def add_comment(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, text = require(p, "card_id", "text")
    action = json_of(trello_request(ctx, "POST", f"cards/{segment(card_id)}/actions/comments", json_body={"text": text}))
    comment = _comment(action)
    return {"comment_id": comment["id"]}, comment, f"Added comment {comment['id']} to the card."


def update_comment(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, comment_id, text = require(p, "card_id", "comment_id", "text")
    trello_request(ctx, "PUT", f"cards/{segment(card_id)}/actions/{segment(comment_id)}/comments", json_body={"text": text})
    return {"comment_id": comment_id}, {"comment_id": comment_id, "text": text}, f"Updated comment {comment_id}."


def delete_comment(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, comment_id = require(p, "card_id", "comment_id")
    trello_request(ctx, "DELETE", f"cards/{segment(card_id)}/actions/{segment(comment_id)}/comments")
    return {"deleted": True}, {"comment_id": comment_id, "deleted": True}, f"Deleted comment {comment_id}."


# ── checklists ───────────────────────────────────────────────────────


def list_checklists(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (card_id,) = require(p, "card_id")
    checklists = [checklist_dict(c) for c in json_of(trello_request(ctx, "GET", f"cards/{segment(card_id)}/checklists"))]
    lines = []
    for c in checklists:
        lines.append(f"{c['name']} (id {c['id']}): {c['completed']}/{c['total']} done")
        lines += [f"  [{'x' if i['complete'] else ' '}] {i['name']} (id {i['id']})" for i in c["items"]]
    return ({"checklists": checklists, "count": len(checklists)}, {"card_id": card_id, "checklists": checklists},
            "\n".join(lines) if lines else "The card has no checklists.")


def create_checklist(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, name = require(p, "card_id", "name")
    checklist = json_of(trello_request(ctx, "POST", "checklists", json_body={"idCard": card_id, "name": name}))
    items = split_ids(p.get("items"))
    for item in items:
        trello_request(ctx, "POST", f"checklists/{segment(checklist['id'])}/checkItems", json_body={"name": item})
    return ({"checklist_id": checklist.get("id", "")}, {**checklist_dict(checklist), "items_added": items},
            f"Created checklist '{name}'" + (f" with {len(items)} item(s)." if items else "."))


def delete_checklist(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (checklist_id,) = require(p, "checklist_id")
    trello_request(ctx, "DELETE", f"checklists/{segment(checklist_id)}")
    return {"deleted": True}, {"checklist_id": checklist_id, "deleted": True}, f"Deleted checklist {checklist_id}."


def add_checklist_item(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    checklist_id, name = require(p, "checklist_id", "name")
    body: dict[str, Any] = {"name": name, "checked": bool(_flag(p.get("checked"))), "pos": p.get("position") or "bottom"}
    if p.get("due"):
        body["due"] = p["due"]
    item = json_of(trello_request(ctx, "POST", f"checklists/{segment(checklist_id)}/checkItems", json_body=body))
    return {"item_id": item.get("id", "")}, item, f"Added '{name}' to the checklist."


def update_checklist_item(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, item_id = require(p, "card_id", "item_id")
    body: dict[str, Any] = {}
    if p.get("name"):
        body["name"] = p["name"]
    complete = _flag(p.get("complete"))
    if complete is not None:
        body["state"] = "complete" if complete else "incomplete"
    if not body:
        raise TrelloAuthError("Nothing to update: give a new name and/or complete.")
    item = json_of(trello_request(ctx, "PUT", f"cards/{segment(card_id)}/checkItem/{segment(item_id)}", json_body=body))
    return ({"item_id": item_id, "state": item.get("state", "")}, item,
            f"Checklist item '{item.get('name', item_id)}' is now {item.get('state', 'updated')}.")


def delete_checklist_item(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    checklist_id, item_id = require(p, "checklist_id", "item_id")
    trello_request(ctx, "DELETE", f"checklists/{segment(checklist_id)}/checkItems/{segment(item_id)}")
    return {"deleted": True}, {"item_id": item_id, "deleted": True}, f"Deleted checklist item {item_id}."


# ── labels ───────────────────────────────────────────────────────────


def _color(value: Any) -> str | None:
    color = str(value or "").strip().lower()
    if not color:
        return None
    if color == "none":
        return "null"
    if color not in COLORS:
        raise TrelloAuthError(f"Unknown label color '{color}'. Use one of: {', '.join(COLORS)}, or none.")
    return color


def list_labels(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (board_id,) = require(p, "board_id")
    labels = [label_dict(l) for l in json_of(trello_request(ctx, "GET", f"boards/{segment(board_id)}/labels", params={"limit": 1000}))]
    return ({"labels": labels, "count": len(labels)}, {"board_id": board_id, "labels": labels},
            "Labels: " + ", ".join(f"{l['name'] or '(no name)'} [{l['color'] or 'no color'}] (id {l['id']})" for l in labels)
            if labels else "The board has no labels.")


def create_label(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    board_id, name = require(p, "board_id", "name")
    label = json_of(trello_request(ctx, "POST", "labels", json_body={"idBoard": board_id, "name": name, "color": _color(p.get("color")) or "null"}))
    return {"label_id": label.get("id", "")}, label_dict(label), f"Created label '{name}'."


def update_label(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (label_id,) = require(p, "label_id")
    body: dict[str, Any] = {}
    if p.get("name"):
        body["name"] = p["name"]
    color = _color(p.get("color"))
    if color:
        body["color"] = color
    if not body:
        raise TrelloAuthError("Nothing to update: give a new name and/or color.")
    label = json_of(trello_request(ctx, "PUT", f"labels/{segment(label_id)}", json_body=body))
    return {"label_id": label_id}, label_dict(label), f"Updated label {label.get('name') or label_id}."


def delete_label(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (label_id,) = require(p, "label_id")
    trello_request(ctx, "DELETE", f"labels/{segment(label_id)}")
    return {"deleted": True}, {"label_id": label_id, "deleted": True}, f"Deleted label {label_id} from the board."


def add_card_label(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, label_id = require(p, "card_id", "label_id")
    trello_request(ctx, "POST", f"cards/{segment(card_id)}/idLabels", json_body={"value": label_id})
    return {"added": True}, {"card_id": card_id, "label_id": label_id}, "Added the label to the card."


def remove_card_label(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, label_id = require(p, "card_id", "label_id")
    trello_request(ctx, "DELETE", f"cards/{segment(card_id)}/idLabels/{segment(label_id)}")
    return {"removed": True}, {"card_id": card_id, "label_id": label_id}, "Removed the label from the card."


# ── lists ────────────────────────────────────────────────────────────


def update_list(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (list_id,) = require(p, "list_id")
    body: dict[str, Any] = {}
    if p.get("name"):
        body["name"] = p["name"]
    archived = _flag(p.get("archived"))
    if archived is not None:
        body["closed"] = archived
    if p.get("position"):
        body["pos"] = p["position"]
    if p.get("board_id"):
        body["idBoard"] = p["board_id"]
    if not body:
        raise TrelloAuthError("Nothing to update: give a name, archived, position or board_id.")
    lst = json_of(trello_request(ctx, "PUT", f"lists/{segment(list_id)}", json_body=body))
    return ({"list_id": list_id, "name": lst.get("name", ""), "archived": bool(lst.get("closed"))},
            {"id": lst.get("id", list_id), "name": lst.get("name", ""), "closed": bool(lst.get("closed"))},
            f"Updated list '{lst.get('name', list_id)}'" + (" (archived)." if lst.get("closed") else "."))


def get_list_cards(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (list_id,) = require(p, "list_id")
    cards = [card_dict(c) for c in json_of(trello_request(ctx, "GET", f"lists/{segment(list_id)}/cards", params={"fields": CARD_FIELDS}))]
    return ({"cards": cards, "count": len(cards)}, {"list_id": list_id, "cards": cards},
            f"{len(cards)} card(s)" + "".join(f"\n- {c['name']} (id {c['id']})" for c in cards[:30]))


# ── board members ────────────────────────────────────────────────────


def _member_type(value: Any) -> str:
    kind = str(value or "normal").strip().lower()
    if kind not in ("normal", "admin", "observer"):
        raise TrelloAuthError("type must be normal, admin or observer.")
    return kind


def list_board_members(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (board_id,) = require(p, "board_id")
    members = [member_dict(m) for m in json_of(trello_request(ctx, "GET", f"boards/{segment(board_id)}/members",
                                                                params={"fields": "username,fullName"}))]
    return ({"members": members, "count": len(members)}, {"board_id": board_id, "members": members},
            "Members: " + ", ".join(f"{m['full_name']} (@{m['username']}, id {m['id']})" for m in members))


def add_board_member(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    board_id, member_id = require(p, "board_id", "member_id")
    trello_request(ctx, "PUT", f"boards/{segment(board_id)}/members/{segment(member_id)}", params={"type": _member_type(p.get("type"))})
    return {"added": True}, {"board_id": board_id, "member_id": member_id}, "Added the member to the board."


def invite_board_member(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    board_id, email = require(p, "board_id", "email")
    body: dict[str, Any] = {"email": email, "type": _member_type(p.get("type"))}
    if p.get("full_name"):
        body["fullName"] = p["full_name"]
    trello_request(ctx, "PUT", f"boards/{segment(board_id)}/members", json_body=body)
    return {"invited": True}, {"board_id": board_id, "email": email}, f"Invited {email} to the board."


def remove_board_member(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    board_id, member_id = require(p, "board_id", "member_id")
    trello_request(ctx, "DELETE", f"boards/{segment(board_id)}/members/{segment(member_id)}")
    return {"removed": True}, {"board_id": board_id, "member_id": member_id}, "Removed the member from the board."


# ── attachments ──────────────────────────────────────────────────────


def list_attachments(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (card_id,) = require(p, "card_id")
    attachments = [attachment_dict(a) for a in json_of(trello_request(ctx, "GET", f"cards/{segment(card_id)}/attachments"))]
    return ({"attachments": attachments, "count": len(attachments)}, {"card_id": card_id, "attachments": attachments},
            f"{len(attachments)} attachment(s)" + "".join(f"\n- {a['name']} (id {a['id']})" for a in attachments))


def add_attachment(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    (card_id,) = require(p, "card_id")
    file = p.get("file")
    name = str(p.get("name") or "").strip()
    link = str(p.get("url") or "").strip()
    text = p.get("file_content")
    if file:
        files = {"file": (name or file.filename or "attachment", file.blob, file.mime_type or "application/octet-stream")}
        attachment = json_of(trello_request(ctx, "POST", f"cards/{segment(card_id)}/attachments", files=files,
                                            data={"name": name or file.filename or "attachment"}, timeout=300))
    elif text:
        if not name:
            raise TrelloAuthError("A file name (such as notes.txt) is required when attaching text.")
        files = {"file": (name, str(text).encode("utf-8"), "text/plain")}
        attachment = json_of(trello_request(ctx, "POST", f"cards/{segment(card_id)}/attachments", files=files,
                                            data={"name": name}, timeout=300))
    elif link:
        if urlparse(link).scheme not in ("http", "https"):
            raise TrelloAuthError("url must be an http(s) link.")
        attachment = json_of(trello_request(ctx, "POST", f"cards/{segment(card_id)}/attachments",
                                            json_body={"url": link, "name": name or link}))
    else:
        raise TrelloAuthError("Give a file, some text content with a file name, or a url to attach.")
    result = attachment_dict(attachment)
    return ({"attachment_id": result["id"], "name": result["name"]}, result, f"Attached {result['name']} to the card.")


def get_attachment(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, attachment_id = require(p, "card_id", "attachment_id")
    info = attachment_dict(json_of(trello_request(ctx, "GET", f"cards/{segment(card_id)}/attachments/{segment(attachment_id)}")))
    out: dict[str, Any] = {"attachment": info, "name": info["name"]}
    if not info["is_upload"]:
        return out, info, f"{info['name']} is a link: {info['url']}"
    if p.get("download") is False or info["size"] > MAX_DOWNLOAD:
        return out, info, f"{info['name']}: {info['size']} bytes, {info['mime_type']}." + (
            f" Over the {MAX_DOWNLOAD // (1024 * 1024)} MB download limit; only its details were returned."
            if info["size"] > MAX_DOWNLOAD else "")
    # Uploaded files are downloaded through the API host with the same Authorization header;
    # the file name comes from the attachment's own URL.
    filename = urlparse(info["url"]).path.rsplit("/", 1)[-1]
    if filename in ("", ".", ".."):
        filename = quote(info["name"], safe="") or "file"
    content = trello_request(ctx, "GET", f"cards/{segment(card_id)}/attachments/{segment(attachment_id)}/download/{filename}",
                             headers={"Accept": "*/*"}, timeout=300).content
    out["_blob"] = (content, {"mime_type": info["mime_type"] or "application/octet-stream", "filename": info["name"]})
    return out, info, f"Downloaded {info['name']} ({len(content)} bytes)."


def delete_attachment(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    card_id, attachment_id = require(p, "card_id", "attachment_id")
    trello_request(ctx, "DELETE", f"cards/{segment(card_id)}/attachments/{segment(attachment_id)}")
    return {"deleted": True}, {"attachment_id": attachment_id, "deleted": True}, f"Deleted attachment {attachment_id}."


# ── workspaces ───────────────────────────────────────────────────────


def list_workspaces(ctx: TrelloContext, p: Mapping[str, Any]) -> Result:
    orgs = json_of(trello_request(ctx, "GET", "members/me/organizations", params={"fields": "id,name,displayName,url"}))
    workspaces = [{"id": o.get("id", ""), "name": o.get("displayName") or o.get("name", ""), "url": o.get("url", "")} for o in orgs]
    return ({"workspaces": workspaces, "count": len(workspaces)}, {"workspaces": workspaces},
            "Workspaces: " + ", ".join(f"{w['name']} (id {w['id']})" for w in workspaces)
            if workspaces else "The account is in no Workspace; create one in Trello first.")
