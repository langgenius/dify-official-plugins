"""
The operations behind the ``google_docs_*`` tools. Each takes the Google context and the tool
parameters and returns (output variables, JSON message, text message); ``run`` handles credentials
and errors, so every tool file is a thin wrapper (Dify loads one Tool class per file).

Content is written from a small Markdown subset - headings (#, ##, ###), bullet (- or *) and
numbered (1.) lists, **bold**, *italic* and [links](url) - and documents are read back as Markdown.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from tools.google_client import GoogleAuthError, GoogleContext, google_request, json_of, require, resolve_context, segment

API = "https://docs.googleapis.com/v1/documents"
DRIVE = "https://www.googleapis.com/drive/v3/files"
DOC_MIME = "application/vnd.google-apps.document"
MAX_TEXT = 50_000

Result = tuple[dict[str, Any], Any, str]


def run(tool: Any, params: Mapping[str, Any], op: Callable[[GoogleContext, Mapping[str, Any]], Result]):
    try:
        ctx = resolve_context(tool.runtime.credentials, tool)
        out, data, text = op(ctx, params)
    except GoogleAuthError as e:
        yield tool.create_text_message(str(e))
        return
    tool._out.update(out, success=True)
    yield tool.create_json_message(data)
    yield tool.create_text_message(text)


def document_id(p: Mapping[str, Any]) -> str:
    """The document ID, also from a full URL (…/document/d/<id>/edit)."""
    (value,) = require(p, "document_id")
    match = re.search(r"/document/d/([A-Za-z0-9_-]+)", value)
    return match.group(1) if match else value


def doc_url(document: str) -> str:
    return f"https://docs.google.com/document/d/{document}/edit"


def get_doc(ctx: GoogleContext, document: str) -> dict[str, Any]:
    return json_of(google_request(ctx, "GET", f"{API}/{segment(document)}"))


def batch(ctx: GoogleContext, document: str, requests: list[dict[str, Any]]) -> dict[str, Any]:
    return json_of(google_request(ctx, "POST", f"{API}/{segment(document)}:batchUpdate", json_body={"requests": requests}))


# ── Markdown in ──────────────────────────────────────────────────────

_INLINE = re.compile(r"\*\*(?P<bold>.+?)\*\*|(?<![*\w])\*(?P<italic>[^*\n]+?)\*(?![*\w])|\[(?P<label>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,3})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")


@dataclass
class Paragraph:
    text: str
    style: str = "NORMAL_TEXT"
    list_kind: str | None = None  # "bullet" or "numbered"
    spans: list[tuple[int, int, dict[str, Any], str]] = field(default_factory=list)  # (start, end, style, fields)


def _utf16_length(text: str) -> int:
    """Google Docs indexes count UTF-16 code units, including both halves of emoji."""
    return len(text.encode("utf-16-le")) // 2


def parse_markdown(content: str) -> list[Paragraph]:
    paragraphs = []
    for line in str(content).replace("\r\n", "\n").split("\n"):
        style, kind, text = "NORMAL_TEXT", None, line.rstrip()
        if m := _HEADING.match(text):
            style, text = f"HEADING_{len(m.group(1))}", m.group(2)
        elif m := _BULLET.match(text):
            kind, text = "bullet", m.group(1)
        elif m := _NUMBERED.match(text):
            kind, text = "numbered", m.group(1)
        plain, spans, pos = "", [], 0
        for m in _INLINE.finditer(text):
            plain += text[pos:m.start()]
            start = _utf16_length(plain)
            if m.group("bold") is not None:
                plain += m.group("bold")
                spans.append((start, _utf16_length(plain), {"bold": True}, "bold"))
            elif m.group("italic") is not None:
                plain += m.group("italic")
                spans.append((start, _utf16_length(plain), {"italic": True}, "italic"))
            else:
                plain += m.group("label")
                spans.append((start, _utf16_length(plain), {"link": {"url": m.group("url")}}, "link"))
            pos = m.end()
        plain += text[pos:]
        paragraphs.append(Paragraph(plain, style, kind, spans))
    while paragraphs and not paragraphs[-1].text and paragraphs[-1].style == "NORMAL_TEXT" and not paragraphs[-1].list_kind:
        paragraphs.pop()
    return paragraphs


def write_requests(paragraphs: list[Paragraph], index: int, prefix_newline: bool, suffix_newline: bool) -> list[dict[str, Any]]:
    """insertText at index, then paragraph styles, lists and inline styles at the inserted positions."""
    body = "\n".join(p.text for p in paragraphs)
    text = ("\n" if prefix_newline else "") + body + ("\n" if suffix_newline else "")
    base = index + (1 if prefix_newline else 0)
    requests: list[dict[str, Any]] = [{"insertText": {"location": {"index": index}, "text": text}}]
    if body:
        # New paragraphs inherit the style around the insertion point: reset them, then style them.
        requests.append({"updateParagraphStyle": {"range": {"startIndex": base, "endIndex": base + _utf16_length(body)},
                                                  "paragraphStyle": {"namedStyleType": "NORMAL_TEXT"}, "fields": "namedStyleType"}})
    offset, ranges = base, []
    for p in paragraphs:
        ranges.append((offset, offset + _utf16_length(p.text)))
        offset += _utf16_length(p.text) + 1
    for p, (start, end) in zip(paragraphs, ranges):
        if p.style != "NORMAL_TEXT" and end > start:
            requests.append({"updateParagraphStyle": {"range": {"startIndex": start, "endIndex": end},
                                                      "paragraphStyle": {"namedStyleType": p.style}, "fields": "namedStyleType"}})
        for s, e, style, fields in p.spans:
            requests.append({"updateTextStyle": {"range": {"startIndex": start + s, "endIndex": start + e}, "textStyle": style, "fields": fields}})
    # Consecutive list items of one kind become one list.
    i = 0
    while i < len(paragraphs):
        kind = paragraphs[i].list_kind
        if not kind:
            i += 1
            continue
        j = i
        while j + 1 < len(paragraphs) and paragraphs[j + 1].list_kind == kind:
            j += 1
        preset = "BULLET_DISC_CIRCLE_SQUARE" if kind == "bullet" else "NUMBERED_DECIMAL_ALPHA_ROMAN"
        requests.append({"createParagraphBullets": {"range": {"startIndex": ranges[i][0], "endIndex": max(ranges[j][1], ranges[j][0] + 1)},
                                                    "bulletPreset": preset}})
        i = j + 1
    return requests


def body_end(document: Mapping[str, Any]) -> tuple[int, bool]:
    """(index of the body's final newline, whether the last paragraph has text)."""
    content = (document.get("body") or {}).get("content") or []
    end = content[-1].get("endIndex", 2) if content else 2
    last = content[-1].get("paragraph") if content else None
    has_text = bool(last and "".join(e.get("textRun", {}).get("content", "") for e in last.get("elements") or []).strip())
    return end - 1, has_text


# ── Markdown out ─────────────────────────────────────────────────────


def _runs(elements: list[Mapping[str, Any]]) -> str:
    out = []
    for element in elements:
        run_ = element.get("textRun")
        if not run_:
            continue
        text = run_.get("content", "").replace("\n", "")
        style = run_.get("textStyle") or {}
        if text.strip() and (style.get("link") or {}).get("url"):
            text = f"[{text}]({style['link']['url']})"
        elif text.strip() and style.get("bold"):
            text = f"**{text}**"
        elif text.strip() and style.get("italic"):
            text = f"*{text}*"
        out.append(text)
    return "".join(out)


def _cell_text(cell: Mapping[str, Any]) -> str:
    return " ".join(_runs(block["paragraph"].get("elements") or []) for block in cell.get("content") or [] if "paragraph" in block).strip()


def to_markdown(document: Mapping[str, Any]) -> tuple[str, list[str]]:
    """The document body as Markdown, and its headings."""
    lists = document.get("lists") or {}
    lines, headings = [], []

    def walk(content: list[Mapping[str, Any]]) -> None:
        for block in content:
            if "paragraph" in block:
                para = block["paragraph"]
                text = _runs(para.get("elements") or [])
                style = (para.get("paragraphStyle") or {}).get("namedStyleType", "")
                if style.startswith("HEADING_") or style == "TITLE":
                    level = 1 if style == "TITLE" else min(int(style.split("_")[1]), 6)
                    headings.append(text)
                    lines.append(f"{'#' * level} {text}")
                elif para.get("bullet"):
                    bullet = para["bullet"]
                    level = bullet.get("nestingLevel", 0)
                    glyph = ((lists.get(bullet.get("listId")) or {}).get("listProperties", {}).get("nestingLevels") or [{}])
                    numbered = "glyphType" in (glyph[min(level, len(glyph) - 1)] if glyph else {})
                    lines.append(f"{'  ' * level}{'1.' if numbered else '-'} {text}")
                else:
                    lines.append(text)
            elif "table" in block:
                rows = block["table"].get("tableRows") or []
                for r, row in enumerate(rows):
                    cells = [_cell_text(cell) for cell in row.get("tableCells") or []]
                    lines.append("| " + " | ".join(cells) + " |")
                    if r == 0:
                        lines.append("|" + " --- |" * len(cells))
                lines.append("")

    walk((document.get("body") or {}).get("content") or [])
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text, headings


# ── tools ────────────────────────────────────────────────────────────


def find_documents(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    name = str(p.get("name") or "").strip()
    query = f"mimeType = '{DOC_MIME}' and trashed = false"
    if name:
        query += " and name contains '" + name.replace("\\", "\\\\").replace("'", "\\'") + "'"
    limit = max(1, min(int(p.get("limit") or 20), 200))
    body = json_of(google_request(ctx, "GET", DRIVE, params={
        "q": query, "pageSize": limit, "orderBy": "modifiedTime desc", "fields": "files(id,name,modifiedTime,webViewLink)",
        "includeItemsFromAllDrives": "true", "supportsAllDrives": "true", "corpora": "allDrives"}))
    docs = [{"id": f.get("id", ""), "name": f.get("name", ""), "modified": f.get("modifiedTime", ""), "url": f.get("webViewLink", "")}
            for f in body.get("files") or []]
    return ({"documents": docs, "count": len(docs)}, {"documents": docs},
            "\n".join(f"- {d['name']} (id {d['id']})" for d in docs) if docs else "No documents found.")


def get_document(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    document = document_id(p)
    doc = get_doc(ctx, document)
    text, headings = to_markdown(doc)
    title = doc.get("title", "")
    cut = text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[… truncated]"
    return ({"title": title, "text": text, "headings": headings, "url": doc_url(document)},
            {"document_id": document, "title": title, "headings": headings, "url": doc_url(document), "length": len(text)},
            f"# {title}\n{doc_url(document)}\n\n{cut}")


def create_document(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (title,) = require(p, "title")
    created = json_of(google_request(ctx, "POST", API, json_body={"title": title}))
    document = created.get("documentId", "")
    content = str(p.get("content") or "")
    if content.strip():
        batch(ctx, document, write_requests(parse_markdown(content), 1, False, False))
    return ({"document_id": document, "url": doc_url(document)}, {"document_id": document, "title": title, "url": doc_url(document)},
            f"Created {title}: {doc_url(document)}")


def append_content(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Add Markdown content at the end (default) or the start of a document."""
    document = document_id(p)
    (content,) = require(p, "content")
    paragraphs = parse_markdown(content)
    if not paragraphs:
        raise GoogleAuthError("content is empty.")
    position = str(p.get("position") or "end")
    if position == "start":
        requests = write_requests(paragraphs, 1, False, True)
    elif position == "end":
        end, has_text = body_end(get_doc(ctx, document))
        requests = write_requests(paragraphs, end, has_text, False)
        if p.get("page_break_before") and has_text:
            requests.append({"insertPageBreak": {"location": {"index": end}}})
    else:
        raise GoogleAuthError("position must be end or start.")
    batch(ctx, document, requests)
    return ({"document_id": document, "paragraphs": len(paragraphs), "url": doc_url(document)},
            {"document_id": document, "paragraphs": len(paragraphs), "position": position},
            f"Added {len(paragraphs)} paragraph(s) at the {position} of the document.")


def replace_text(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Replace every occurrence of text: one find/replace pair, or a JSON object of several (template placeholders)."""
    document = document_id(p)
    pairs: dict[str, str] = {}
    if p.get("replacements"):
        raw = p["replacements"]
        try:
            pairs = raw if isinstance(raw, dict) else json.loads(str(raw))
        except ValueError as e:
            raise GoogleAuthError(f'replacements must be a JSON object, e.g. {{"{{{{name}}}}": "Kim"}}: {e}') from e
        if not isinstance(pairs, dict):
            raise GoogleAuthError("replacements must be a JSON object of text → replacement.")
    if p.get("find"):
        pairs[str(p["find"])] = str(p.get("replace") or "")
    if not pairs:
        raise GoogleAuthError("Give find (and replace), or replacements.")
    match_case = p.get("match_case") is not False
    requests = [{"replaceAllText": {"containsText": {"text": str(k), "matchCase": match_case}, "replaceText": "" if v is None else str(v)}}
                for k, v in pairs.items()]
    replies = batch(ctx, document, requests).get("replies") or []
    counts = {k: int((r.get("replaceAllText") or {}).get("occurrencesChanged") or 0) for k, r in zip(pairs, replies)}
    total = sum(counts.values())
    return ({"replaced": total}, {"document_id": document, "replaced": counts},
            f"Replaced {total} occurrence(s): " + ", ".join(f"'{k}' ×{n}" for k, n in counts.items()))


def insert_table(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Add a table at the end of a document, filled from a JSON grid (the first row is usually the header)."""
    document = document_id(p)
    raw = p.get("values")
    try:
        values = raw if isinstance(raw, list) else json.loads(str(raw or ""))
    except ValueError as e:
        raise GoogleAuthError(f'values must be a JSON array of rows, e.g. [["Name", "Score"], ["Kim", 90]]: {e}') from e
    if not isinstance(values, list) or not values or not all(isinstance(r, list) and r for r in values):
        raise GoogleAuthError('values must be a JSON array of rows, e.g. [["Name", "Score"], ["Kim", 90]].')
    rows, columns = len(values), max(len(r) for r in values)
    if rows * columns > 2000:
        raise GoogleAuthError("The table is too large (at most 2000 cells).")
    batch(ctx, document, [{"insertTable": {"rows": rows, "columns": columns, "endOfSegmentLocation": {"segmentId": ""}}}])
    doc = get_doc(ctx, document)
    tables = [b for b in (doc.get("body") or {}).get("content") or [] if "table" in b]
    if not tables:
        raise GoogleAuthError("The table was inserted but could not be found to fill it.")
    inserts = []
    for r, row in enumerate(tables[-1]["table"].get("tableRows") or []):
        for c, cell in enumerate(row.get("tableCells") or []):
            value = values[r][c] if r < len(values) and c < len(values[r]) else ""
            if value not in ("", None):
                inserts.append((cell["content"][0]["startIndex"], str(value), r == 0 and bool(p.get("bold_header", True))))
    # Bottom-up, so each insertion leaves the earlier cells' positions unchanged.
    requests = []
    for index, text, bold in sorted(inserts, reverse=True):
        requests.append({"insertText": {"location": {"index": index}, "text": text}})
        if bold:
            requests.append({"updateTextStyle": {"range": {"startIndex": index, "endIndex": index + _utf16_length(text)}, "textStyle": {"bold": True}, "fields": "bold"}})
    if requests:
        batch(ctx, document, requests)
    return ({"rows": rows, "columns": columns}, {"document_id": document, "rows": rows, "columns": columns},
            f"Added a {rows}×{columns} table at the end of the document.")
