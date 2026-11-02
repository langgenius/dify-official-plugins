"""
The operations behind the ``google_drive_*`` tools. Each takes the Google context and the tool
parameters and returns (output variables, JSON message, text message); ``run`` handles credentials
and errors, so every tool file is a thin wrapper (Dify loads one Tool class per file).

Every call works across My Drive and shared drives (``supportsAllDrives``). Google Docs, Sheets
and Slides have no file content of their own: they are exported (to Markdown, CSV, PDF, Office...).
"""

import json
import mimetypes
import secrets
from typing import Any, Callable, Mapping

from tools.google_client import GoogleAuthError, GoogleContext, google_request, json_of, require, resolve_context, segment

API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
FILE_FIELDS = "id,name,mimeType,size,modifiedTime,createdTime,webViewLink,parents,trashed,driveId,owners(displayName,emailAddress)"
ALL_DRIVES = {"supportsAllDrives": "true"}
# Larger files are described but not downloaded into the conversation (Google exports stop at 10 MB anyway).
MAX_DOWNLOAD = 50 * 1024 * 1024
MAX_TEXT = 50_000

# Google-native types: what "read as text" exports them to, and the formats "download" can export to.
TEXT_EXPORT = {
    "application/vnd.google-apps.document": ["text/markdown", "text/plain"],
    "application/vnd.google-apps.spreadsheet": ["text/csv"],
    "application/vnd.google-apps.presentation": ["text/plain"],
    "application/vnd.google-apps.drawing": [],
}
EXPORT_FORMATS = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "csv": "text/csv",
    "md": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
    "png": "image/png",
}
DEFAULT_EXPORT = {
    "application/vnd.google-apps.document": "docx",
    "application/vnd.google-apps.spreadsheet": "xlsx",
    "application/vnd.google-apps.presentation": "pptx",
    "application/vnd.google-apps.drawing": "png",
}
CONVERT_TO = {"document": "application/vnd.google-apps.document", "spreadsheet": "application/vnd.google-apps.spreadsheet",
              "presentation": "application/vnd.google-apps.presentation"}
ROLES = ("reader", "commenter", "writer", "fileOrganizer", "organizer")

Result = tuple[dict[str, Any], Any, str]


def run(tool: Any, params: Mapping[str, Any], op: Callable[[GoogleContext, Mapping[str, Any]], Result]):
    try:
        ctx = resolve_context(tool.runtime.credentials, tool)
        out, data, text = op(ctx, params)
    except GoogleAuthError as e:
        yield tool.create_text_message(str(e))
        return
    blob = out.pop("_blob", None)
    tool._out.update(out, success=True)
    yield tool.create_json_message(data)
    if blob is not None:
        yield tool.create_blob_message(blob[0], meta=blob[1])
    yield tool.create_text_message(text)


# ── helpers ──────────────────────────────────────────────────────────


def q_string(value: str) -> str:
    """A value inside a Drive query: single-quoted, with \\ and ' escaped."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


# Types for text the agent writes; the platform's mimetypes table differs (Windows maps .csv to Excel).
TEXT_TYPES = {"csv": "text/csv", "md": "text/markdown", "html": "text/html", "htm": "text/html", "json": "application/json",
              "xml": "application/xml", "tsv": "text/tab-separated-values"}


def text_type(name: str) -> str:
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return TEXT_TYPES.get(extension) or (mimetypes.guess_type(name)[0] if extension else None) or "text/plain"


def file_dict(f: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": f.get("id", ""),
        "name": f.get("name", ""),
        "mime_type": f.get("mimeType", ""),
        "is_folder": f.get("mimeType") == FOLDER,
        "size": int(f.get("size") or 0),
        "modified": f.get("modifiedTime", ""),
        "url": f.get("webViewLink", ""),
        "parents": list(f.get("parents") or []),
        "owner": ((f.get("owners") or [{}])[0]).get("emailAddress", ""),
        "trashed": bool(f.get("trashed")),
    }


def get_meta(ctx: GoogleContext, file_id: str) -> dict[str, Any]:
    return json_of(google_request(ctx, "GET", f"{API}/files/{segment(file_id)}", params={"fields": FILE_FIELDS, **ALL_DRIVES}))


def folder_id(p: Mapping[str, Any], key: str = "folder_id") -> str:
    return str(p.get(key) or "").strip() or "root"


def list_files(ctx: GoogleContext, query: str, limit: int, order_by: str | None = None) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    params: dict[str, Any] = {"q": query, "fields": f"nextPageToken,files({FILE_FIELDS})", "pageSize": min(100, limit),
                              "includeItemsFromAllDrives": "true", "corpora": "allDrives", "orderBy": order_by, **ALL_DRIVES}
    while len(files) < limit:
        body = json_of(google_request(ctx, "GET", f"{API}/files", params=params))
        files.extend(body.get("files") or [])
        if not body.get("nextPageToken"):
            break
        params["pageToken"] = body["nextPageToken"]
    return [file_dict(f) for f in files[:limit]]


def _limit(p: Mapping[str, Any], default: int, maximum: int) -> int:
    try:
        return max(1, min(int(p.get("limit") or default), maximum))
    except (TypeError, ValueError):
        return default


def _listing(files: list[dict[str, Any]]) -> str:
    return "\n".join(f"- {'📁 ' if f['is_folder'] else ''}{f['name']} (id {f['id']})" for f in files[:40])


# ── find and read ────────────────────────────────────────────────────


def search(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Files by name / content / type / folder, or a raw Drive query."""
    query = str(p.get("query") or "").strip()
    if not query:
        parts = ["trashed = false"]
        name = str(p.get("name") or "").strip()
        if name:
            parts.append(f"name contains {q_string(name)}")
        text = str(p.get("text") or "").strip()
        if text:
            parts.append(f"fullText contains {q_string(text)}")
        kind = str(p.get("file_type") or "any")
        types = {"folder": FOLDER, "document": CONVERT_TO["document"], "spreadsheet": CONVERT_TO["spreadsheet"],
                 "presentation": CONVERT_TO["presentation"], "pdf": "application/pdf"}
        if kind in types:
            parts.append(f"mimeType = {q_string(types[kind])}")
        if p.get("folder_id"):
            parts.append(f"{q_string(str(p['folder_id']).strip())} in parents")
        if len(parts) == 1 and not p.get("recent"):
            raise GoogleAuthError("Give a name, text, file_type, folder_id or a raw query.")
        query = " and ".join(parts)
    files = list_files(ctx, query, _limit(p, 25, 500), "modifiedTime desc" if "fullText" not in query else None)
    return ({"files": files, "count": len(files)}, {"query": query, "files": files},
            f"Found {len(files)} file(s):\n{_listing(files)}" if files else f"Nothing matches: {query}")


def list_folder(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    folder = folder_id(p)
    query = f"{q_string(folder)} in parents and trashed = false"
    files = list_files(ctx, query, _limit(p, 100, 1000), "folder,name")
    return ({"files": files, "count": len(files)}, {"folder_id": folder, "files": files},
            f"{len(files)} item(s) in the folder:\n{_listing(files)}" if files else "The folder is empty.")


def get_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (file_id,) = require(p, "file_id")
    info = file_dict(get_meta(ctx, file_id))
    return ({"file": info, "name": info["name"], "url": info["url"], "mime_type": info["mime_type"]}, info,
            f"{info['name']} ({info['mime_type']}, {info['size']} bytes, modified {info['modified']})\n{info['url']}")


def read_text(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """The text of a Doc (Markdown), Sheet (CSV of the first sheet), Slides deck or text file."""
    (file_id,) = require(p, "file_id")
    meta = get_meta(ctx, file_id)
    mime = meta.get("mimeType", "")
    text = None
    if mime in TEXT_EXPORT:
        for target in TEXT_EXPORT[mime]:
            try:
                text = google_request(ctx, "GET", f"{API}/files/{segment(file_id)}/export", params={"mimeType": target}).content.decode("utf-8", "replace")
                break
            except GoogleAuthError:
                continue
        if text is None:
            raise GoogleAuthError(f"{meta.get('name')} ({mime}) cannot be read as text; use google_drive_download_file.")
    elif mime.startswith("text/") or mime in ("application/json", "application/xml", "application/javascript"):
        if int(meta.get("size") or 0) > MAX_DOWNLOAD:
            raise GoogleAuthError("The file is too large to read here; use google_drive_download_file.")
        text = google_request(ctx, "GET", f"{API}/files/{segment(file_id)}", params={"alt": "media", **ALL_DRIVES}).content.decode("utf-8", "replace")
    else:
        raise GoogleAuthError(f"{meta.get('name')} is a {mime or 'binary'} file, not text: use google_drive_download_file to get it.")
    cut = text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[… truncated]"
    return ({"text": text, "name": meta.get("name", ""), "mime_type": mime},
            {"file_id": file_id, "name": meta.get("name", ""), "mime_type": mime, "length": len(text)}, f"# {meta.get('name', '')}\n\n{cut}")


def download_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (file_id,) = require(p, "file_id")
    meta = get_meta(ctx, file_id)
    mime, name = meta.get("mimeType", ""), meta.get("name", "file")
    if mime == FOLDER:
        raise GoogleAuthError(f"{name} is a folder; use google_drive_list_folder.")
    if mime.startswith("application/vnd.google-apps."):
        fmt = str(p.get("export_format") or DEFAULT_EXPORT.get(mime, "pdf")).lower().lstrip(".")
        if fmt not in EXPORT_FORMATS:
            raise GoogleAuthError(f"export_format must be one of: {', '.join(EXPORT_FORMATS)}.")
        target = EXPORT_FORMATS[fmt]
        content = google_request(ctx, "GET", f"{API}/files/{segment(file_id)}/export", params={"mimeType": target}, timeout=300).content
        out_name, out_mime = f"{name}.{fmt}", target
    else:
        if int(meta.get("size") or 0) > MAX_DOWNLOAD:
            raise GoogleAuthError(f"{name} is over the {MAX_DOWNLOAD // (1024 * 1024)} MB download limit.")
        content = google_request(ctx, "GET", f"{API}/files/{segment(file_id)}", params={"alt": "media", **ALL_DRIVES},
                                 headers={"Accept": "*/*"}, timeout=300).content
        out_name, out_mime = name, mime or "application/octet-stream"
    info = file_dict(meta)
    return ({"file": info, "name": out_name, "size": len(content), "_blob": (content, {"mime_type": out_mime, "filename": out_name})},
            info, f"Downloaded {out_name} ({len(content)} bytes).")


def list_shared_drives(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    drives = [{"id": d.get("id", ""), "name": d.get("name", "")}
              for d in json_of(google_request(ctx, "GET", f"{API}/drives", params={"pageSize": 100})).get("drives") or []]
    return ({"drives": drives, "count": len(drives)}, {"drives": drives},
            "Shared drives: " + ", ".join(f"{d['name']} (id {d['id']})" for d in drives) if drives else "No shared drives.")


# ── write ────────────────────────────────────────────────────────────


def upload_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Upload a file (or text written by the agent); optionally convert it to a Google Doc / Sheet / Slides."""
    file = p.get("file")
    name = str(p.get("name") or "").strip()
    if file:
        content, name, mime = file.blob, name or file.filename or "file", file.mime_type
    elif p.get("text_content"):
        if not name:
            raise GoogleAuthError("A file name (such as notes.txt) is required when uploading text.")
        content, mime = str(p["text_content"]).encode("utf-8"), text_type(name)
    else:
        raise GoogleAuthError("Give a file, or text_content with a name.")
    metadata: dict[str, Any] = {"name": name, "parents": [folder_id(p)]}
    convert = str(p.get("convert_to") or "none")
    if convert in CONVERT_TO:
        metadata["mimeType"] = CONVERT_TO[convert]
    boundary = secrets.token_hex(16)
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: {mime or 'application/octet-stream'}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    created = json_of(google_request(ctx, "POST", UPLOAD, params={"uploadType": "multipart", "fields": FILE_FIELDS, **ALL_DRIVES},
                                     data=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"}, timeout=300))
    info = file_dict(created)
    return ({"file_id": info["id"], "name": info["name"], "url": info["url"]}, info, f"Uploaded {info['name']}: {info['url']}")


def create_folder(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (name,) = require(p, "name")
    created = json_of(google_request(ctx, "POST", f"{API}/files", params={"fields": FILE_FIELDS, **ALL_DRIVES},
                                     json_body={"name": name, "mimeType": FOLDER, "parents": [folder_id(p, "parent_id")]}))
    info = file_dict(created)
    return {"folder_id": info["id"], "url": info["url"]}, info, f"Created folder {info['name']} (id {info['id']})."


def copy_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (file_id,) = require(p, "file_id")
    body: dict[str, Any] = {}
    if p.get("name"):
        body["name"] = str(p["name"])
    if p.get("folder_id"):
        body["parents"] = [str(p["folder_id"]).strip()]
    copied = json_of(google_request(ctx, "POST", f"{API}/files/{segment(file_id)}/copy", params={"fields": FILE_FIELDS, **ALL_DRIVES},
                                    json_body=body))
    info = file_dict(copied)
    return {"file_id": info["id"], "url": info["url"]}, info, f"Copied to {info['name']} (id {info['id']})."


def move_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    file_id, target = require(p, "file_id", "folder_id")
    current = ",".join(get_meta(ctx, file_id).get("parents") or [])
    moved = json_of(google_request(ctx, "PATCH", f"{API}/files/{segment(file_id)}", json_body={}, params={
        "addParents": target, "removeParents": current or None, "fields": FILE_FIELDS, **ALL_DRIVES}))
    info = file_dict(moved)
    return {"file_id": info["id"], "parents": info["parents"]}, info, f"Moved {info['name']}."


def rename_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    file_id, name = require(p, "file_id", "name")
    body: dict[str, Any] = {"name": name}
    if p.get("description") is not None and str(p.get("description")).strip():
        body["description"] = str(p["description"])
    renamed = json_of(google_request(ctx, "PATCH", f"{API}/files/{segment(file_id)}", json_body=body,
                                     params={"fields": FILE_FIELDS, **ALL_DRIVES}))
    info = file_dict(renamed)
    return {"file_id": info["id"], "name": info["name"]}, info, f"Renamed to {info['name']}."


def delete_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Move to the trash (default), restore, or delete permanently."""
    (file_id,) = require(p, "file_id")
    mode = str(p.get("mode") or "trash")
    url = f"{API}/files/{segment(file_id)}"
    if mode == "permanent":
        google_request(ctx, "DELETE", url, params=ALL_DRIVES)
        text = "Deleted the file permanently."
    elif mode in ("trash", "restore"):
        google_request(ctx, "PATCH", url, json_body={"trashed": mode == "trash"}, params=ALL_DRIVES)
        text = "Moved the file to the trash." if mode == "trash" else "Restored the file from the trash."
    else:
        raise GoogleAuthError("mode must be trash, restore or permanent.")
    return {"file_id": file_id, "mode": mode}, {"file_id": file_id, "mode": mode}, text


# ── sharing ──────────────────────────────────────────────────────────


def share_file(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Give a person, a group, a domain or anyone with the link access to a file or folder."""
    (file_id,) = require(p, "file_id")
    role = str(p.get("role") or "reader")
    if role not in ROLES:
        raise GoogleAuthError(f"role must be one of: {', '.join(ROLES)}.")
    email = str(p.get("email") or "").strip()
    domain = str(p.get("domain") or "").strip()
    permission: dict[str, Any] = {"role": role}
    params: dict[str, Any] = {"fields": "id,type,role,emailAddress,domain", **ALL_DRIVES}
    if email:
        permission.update(type="group" if p.get("is_group") else "user", emailAddress=email)
        params["sendNotificationEmail"] = "false" if p.get("notify") is False else "true"
        if p.get("message") and params["sendNotificationEmail"] == "true":
            params["emailMessage"] = str(p["message"])
    elif domain:
        permission.update(type="domain", domain=domain)
    elif p.get("anyone_with_link"):
        permission.update(type="anyone")
    else:
        raise GoogleAuthError("Give an email, a domain, or anyone_with_link=true.")
    created = json_of(google_request(ctx, "POST", f"{API}/files/{segment(file_id)}/permissions", params=params, json_body=permission))
    url = get_meta(ctx, file_id).get("webViewLink", "")
    who = email or domain or "anyone with the link"
    return ({"permission_id": created.get("id", ""), "url": url}, {"permission": created, "url": url},
            f"Shared with {who} as {role}. Link: {url}")


def list_permissions(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (file_id,) = require(p, "file_id")
    body = json_of(google_request(ctx, "GET", f"{API}/files/{segment(file_id)}/permissions",
                                  params={"fields": "permissions(id,type,role,emailAddress,domain,displayName)", **ALL_DRIVES}))
    perms = [{"id": x.get("id", ""), "type": x.get("type", ""), "role": x.get("role", ""),
              "who": x.get("emailAddress") or x.get("domain") or ("anyone with the link" if x.get("type") == "anyone" else x.get("displayName", ""))}
             for x in body.get("permissions") or []]
    return ({"permissions": perms, "count": len(perms)}, {"file_id": file_id, "permissions": perms},
            "Access: " + "; ".join(f"{x['who']} ({x['role']}, id {x['id']})" for x in perms))


def remove_permission(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Stop sharing with a person (by email) or remove a permission by ID ("anyone" ends link sharing)."""
    (file_id,) = require(p, "file_id")
    target = str(p.get("email") or p.get("permission_id") or "").strip()
    if not target:
        raise GoogleAuthError("Give the email to stop sharing with, a permission_id, or 'anyone' for link sharing.")
    permission_id = target
    if "@" in target or target.lower() == "anyone":
        perms = list_permissions(ctx, {"file_id": file_id})[0]["permissions"]
        match = [x for x in perms if x["who"].lower() == target.lower() or (target.lower() == "anyone" and x["type"] == "anyone")]
        if not match:
            raise GoogleAuthError(f"The file is not shared with {target}.")
        if match[0]["role"] == "owner":
            raise GoogleAuthError("The owner's access cannot be removed.")
        permission_id = match[0]["id"]
    google_request(ctx, "DELETE", f"{API}/files/{segment(file_id)}/permissions/{segment(permission_id)}", params=ALL_DRIVES)
    return {"removed": True}, {"file_id": file_id, "permission_id": permission_id}, f"Stopped sharing with {target}."
