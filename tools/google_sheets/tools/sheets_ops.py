"""
The operations behind the ``google_sheets_*`` tools. Each takes the Google context and the tool
parameters and returns (output variables, JSON message, text message); ``run`` handles credentials
and errors, so every tool file is a thin wrapper (Dify loads one Tool class per file).

Rows are objects keyed by the header row ({"Name": "Kim", "Score": 90}), the way agents and
workflows think; raw A1 ranges are there too. Values are written as if typed (USER_ENTERED), so
numbers, dates and formulas behave as in the Sheets UI.
"""

import json
import re
from typing import Any, Callable, Mapping

from tools.google_client import GoogleAuthError, GoogleContext, google_request, json_of, require, resolve_context, segment

API = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE = "https://www.googleapis.com/drive/v3/files"
SHEET_MIME = "application/vnd.google-apps.spreadsheet"
MAX_ROWS = 5000

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


# ── helpers ──────────────────────────────────────────────────────────


def spreadsheet_id(p: Mapping[str, Any]) -> str:
    """The spreadsheet ID, also from a full URL (…/spreadsheets/d/<id>/edit)."""
    (value,) = require(p, "spreadsheet_id")
    match = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]+)", value)
    return match.group(1) if match else value


def quote_sheet(name: str) -> str:
    """A sheet name as used in A1 notation: 'My sheet' (quotes doubled)."""
    return "'" + name.replace("'", "''") + "'"


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def spreadsheet_meta(ctx: GoogleContext, sid: str) -> dict[str, Any]:
    return json_of(google_request(ctx, "GET", f"{API}/{segment(sid)}", params={
        "fields": "spreadsheetId,spreadsheetUrl,properties(title,timeZone),sheets(properties(sheetId,title,index,gridProperties))"}))


def sheet_props(ctx: GoogleContext, sid: str, sheet: str | None) -> dict[str, Any]:
    """The properties of a sheet by name (case-insensitive) or the first sheet when none is given."""
    sheets = [s["properties"] for s in spreadsheet_meta(ctx, sid).get("sheets") or []]
    if not sheets:
        raise GoogleAuthError("The spreadsheet has no sheets.")
    if not sheet:
        return sheets[0]
    for props in sheets:
        if props.get("title", "").lower() == sheet.strip().lower():
            return props
    raise GoogleAuthError(f"No sheet named '{sheet}'. Sheets: {', '.join(s.get('title', '') for s in sheets)}.")


def get_values(ctx: GoogleContext, sid: str, a1: str, render: str = "FORMATTED_VALUE") -> list[list[Any]]:
    body = json_of(google_request(ctx, "GET", f"{API}/{segment(sid)}/values/{segment(a1)}", params={"valueRenderOption": render}))
    return body.get("values") or []


def _header_row(p: Mapping[str, Any]) -> int:
    try:
        return max(1, int(p.get("header_row") or 1))
    except (TypeError, ValueError):
        return 1


def read_table(ctx: GoogleContext, p: Mapping[str, Any]) -> tuple[str, dict[str, Any], list[str], list[dict[str, Any]]]:
    """(spreadsheet ID, sheet properties, headers, rows with their sheet row numbers)."""
    sid = spreadsheet_id(p)
    props = sheet_props(ctx, sid, str(p.get("sheet") or "").strip() or None)
    values = get_values(ctx, sid, quote_sheet(props["title"]), str(p.get("value_render") or "FORMATTED_VALUE"))
    header_at = _header_row(p)
    if len(values) < header_at:
        return sid, props, [], []
    headers = [str(h).strip() for h in values[header_at - 1]]
    rows = []
    for offset, raw in enumerate(values[header_at:], start=header_at + 1):
        if not any(str(v).strip() for v in raw):
            continue
        record = {h: (raw[i] if i < len(raw) else "") for i, h in enumerate(headers) if h}
        record["_row"] = offset
        rows.append(record)
    return sid, props, headers, rows


def parse_rows(value: Any) -> list[dict[str, Any]]:
    """Rows given as a JSON array of objects (or one object)."""
    if isinstance(value, list):
        rows = value
    elif isinstance(value, Mapping):
        rows = [value]
    else:
        try:
            rows = json.loads(str(value or "").strip() or "[]")
        except ValueError as e:
            raise GoogleAuthError(f'rows must be JSON, e.g. [{{"Name": "Kim", "Score": 90}}]: {e}') from e
        rows = [rows] if isinstance(rows, dict) else rows
    if not isinstance(rows, list) or not all(isinstance(r, Mapping) for r in rows) or not rows:
        raise GoogleAuthError('rows must be a JSON array of objects keyed by column header, e.g. [{"Name": "Kim", "Score": 90}].')
    return [dict(r) for r in rows]


def _column_index(headers: list[str], name: str) -> int:
    lowered = [h.lower() for h in headers]
    if name.lower() not in lowered:
        raise GoogleAuthError(f"No column '{name}'. Columns: {', '.join(h for h in headers if h)}.")
    return lowered.index(name.lower())


def _check_columns(headers: list[str], rows: list[dict[str, Any]], add_missing: bool) -> list[str]:
    """Columns the rows use that the sheet lacks: added to the header row, or an error."""
    known = {h.lower() for h in headers}
    missing = list(dict.fromkeys(k for r in rows for k in r if k.lower() not in known and k != "_row"))
    if missing and not add_missing:
        raise GoogleAuthError(f"Unknown column(s) {missing}. Columns: {', '.join(h for h in headers if h)}. "
                              "Set add_missing_columns to add them to the header row.")
    return missing


def _matches(row: Mapping[str, Any], key: str, value: Any) -> bool:
    return str(row.get(key, "")).strip().lower() == str(value).strip().lower()


def _write_header(ctx: GoogleContext, sid: str, props: dict[str, Any], header_at: int, headers: list[str]) -> None:
    a1 = f"{quote_sheet(props['title'])}!A{header_at}"
    google_request(ctx, "PUT", f"{API}/{segment(sid)}/values/{segment(a1)}", params={"valueInputOption": "USER_ENTERED"},
                   json_body={"values": [headers]})


def _cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _public(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{("row_number" if k == "_row" else k): v for k, v in r.items()} for r in rows]


# ── spreadsheets ─────────────────────────────────────────────────────


def find_spreadsheets(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    name = str(p.get("name") or "").strip()
    query = f"mimeType = '{SHEET_MIME}' and trashed = false"
    if name:
        query += " and name contains '" + name.replace("\\", "\\\\").replace("'", "\\'") + "'"
    limit = max(1, min(int(p.get("limit") or 20), 200))
    body = json_of(google_request(ctx, "GET", DRIVE, params={
        "q": query, "pageSize": limit, "orderBy": "modifiedTime desc", "fields": "files(id,name,modifiedTime,webViewLink)",
        "includeItemsFromAllDrives": "true", "supportsAllDrives": "true", "corpora": "allDrives"}))
    files = [{"id": f.get("id", ""), "name": f.get("name", ""), "modified": f.get("modifiedTime", ""), "url": f.get("webViewLink", "")}
             for f in body.get("files") or []]
    return ({"spreadsheets": files, "count": len(files)}, {"spreadsheets": files},
            "\n".join(f"- {f['name']} (id {f['id']})" for f in files) if files else "No spreadsheets found.")


def get_spreadsheet(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    meta = spreadsheet_meta(ctx, spreadsheet_id(p))
    sheets = [{"sheet_id": s["properties"].get("sheetId"), "title": s["properties"].get("title", ""),
               "rows": (s["properties"].get("gridProperties") or {}).get("rowCount", 0),
               "columns": (s["properties"].get("gridProperties") or {}).get("columnCount", 0)} for s in meta.get("sheets") or []]
    title = (meta.get("properties") or {}).get("title", "")
    return ({"title": title, "sheets": sheets, "url": meta.get("spreadsheetUrl", "")},
            {"spreadsheet_id": meta.get("spreadsheetId", ""), "title": title, "url": meta.get("spreadsheetUrl", ""), "sheets": sheets},
            f"{title}: sheets " + ", ".join(s["title"] for s in sheets))


def create_spreadsheet(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (title,) = require(p, "title")
    names = [n.strip() for n in str(p.get("sheets") or "").split(",") if n.strip()] or ["Sheet1"]
    created = json_of(google_request(ctx, "POST", API, json_body={
        "properties": {"title": title}, "sheets": [{"properties": {"title": n}} for n in names]}))
    sid = created.get("spreadsheetId", "")
    headers = [h.strip() for h in str(p.get("headers") or "").split(",") if h.strip()]
    if headers:
        _write_header(ctx, sid, created["sheets"][0]["properties"], 1, headers)
    return ({"spreadsheet_id": sid, "url": created.get("spreadsheetUrl", "")},
            {"spreadsheet_id": sid, "url": created.get("spreadsheetUrl", ""), "sheets": names, "headers": headers},
            f"Created spreadsheet {title}: {created.get('spreadsheetUrl', '')}")


def add_sheet(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    sid = spreadsheet_id(p)
    (title,) = require(p, "title")
    reply = json_of(google_request(ctx, "POST", f"{API}/{segment(sid)}:batchUpdate",
                                   json_body={"requests": [{"addSheet": {"properties": {"title": title}}}]}))
    props = reply["replies"][0]["addSheet"]["properties"]
    return {"sheet_id": props.get("sheetId", 0), "title": props.get("title", title)}, props, f"Added sheet {props.get('title', title)}."


def delete_sheet(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    sid = spreadsheet_id(p)
    (sheet,) = require(p, "sheet")
    props = sheet_props(ctx, sid, sheet)
    google_request(ctx, "POST", f"{API}/{segment(sid)}:batchUpdate", json_body={"requests": [{"deleteSheet": {"sheetId": props["sheetId"]}}]})
    return {"deleted": True}, {"sheet": props["title"], "deleted": True}, f"Deleted sheet {props['title']}."


def rename_sheet(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    sid = spreadsheet_id(p)
    sheet, new = require(p, "sheet", "new_title")
    props = sheet_props(ctx, sid, sheet)
    google_request(ctx, "POST", f"{API}/{segment(sid)}:batchUpdate", json_body={"requests": [{"updateSheetProperties": {
        "properties": {"sheetId": props["sheetId"], "title": new}, "fields": "title"}}]})
    return {"title": new}, {"sheet_id": props["sheetId"], "title": new}, f"Renamed {props['title']} to {new}."


# ── rows ─────────────────────────────────────────────────────────────


def read_rows(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Rows as objects keyed by the header row, optionally only those whose column equals a value."""
    sid, props, headers, rows = read_table(ctx, p)
    column = str(p.get("filter_column") or "").strip()
    if column:
        key = headers[_column_index(headers, column)]
        rows = [r for r in rows if _matches(r, key, p.get("filter_value", ""))]
    limit = max(1, min(int(p.get("limit") or 500), MAX_ROWS))
    shown = _public(rows[:limit])
    text = (f"{len(rows)} row(s) in {props['title']}" + (f" (first {limit} shown)" if len(rows) > limit else "") + ":\n"
            + "\n".join(json.dumps(r, ensure_ascii=False) for r in shown[:50]))
    return ({"rows": shown, "count": len(rows), "headers": [h for h in headers if h]},
            {"sheet": props["title"], "headers": headers, "rows": shown}, text if rows else f"No rows in {props['title']}.")


def append_rows(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    sid, props, headers, _ = read_table(ctx, p)
    rows = parse_rows(p.get("rows"))
    if not any(headers):
        headers = list(dict.fromkeys(k for r in rows for k in r))
        _write_header(ctx, sid, props, _header_row(p), headers)
    missing = _check_columns(headers, rows, bool(p.get("add_missing_columns")))
    if missing:
        headers = headers + missing
        _write_header(ctx, sid, props, _header_row(p), headers)
    values = [[_cell(next((r[k] for k in r if k.lower() == h.lower()), "")) for h in headers] for r in rows]
    a1 = f"{quote_sheet(props['title'])}!A{_header_row(p)}"
    result = json_of(google_request(ctx, "POST", f"{API}/{segment(sid)}/values/{segment(a1)}:append",
                                    params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
                                    json_body={"values": values}))
    updated = (result.get("updates") or {}).get("updatedRange", "")
    return ({"appended": len(values), "range": updated}, {"appended": len(values), "range": updated, "added_columns": missing},
            f"Appended {len(values)} row(s) to {props['title']} ({updated})." + (f" Added columns: {', '.join(missing)}." if missing else ""))


def _update(ctx: GoogleContext, p: Mapping[str, Any], upsert: bool) -> Result:
    sid, props, headers, existing = read_table(ctx, p)
    (key_column,) = require(p, "key_column")
    key = headers[_column_index(headers, key_column)] if any(headers) else key_column
    rows = parse_rows(p.get("rows"))
    missing = _check_columns(headers, rows, bool(p.get("add_missing_columns")))
    if missing:
        headers = headers + missing
        _write_header(ctx, sid, props, _header_row(p), headers)
    update_all = bool(p.get("update_all_matches"))
    data, to_append, not_found, updated_rows = [], [], [], 0
    for row in rows:
        value = next((row[k] for k in row if k.lower() == key.lower()), None)
        if value is None or str(value) == "":
            raise GoogleAuthError(f"Every row needs a value for the key column '{key}'.")
        matches = [r for r in existing if _matches(r, key, value)]
        if not matches:
            (to_append if upsert else not_found).append(row)
            continue
        for match in matches if update_all else matches[:1]:
            updated_rows += 1
            for column, cell in row.items():
                index = _column_index(headers, column)
                data.append({"range": f"{quote_sheet(props['title'])}!{column_letter(index)}{match['_row']}", "values": [[_cell(cell)]]})
    if data:
        google_request(ctx, "POST", f"{API}/{segment(sid)}/values:batchUpdate",
                       json_body={"valueInputOption": "USER_ENTERED", "data": data})
    appended = 0
    if to_append:
        appended = append_rows(ctx, {**p, "rows": to_append, "add_missing_columns": True})[0]["appended"]
    text = f"Updated {updated_rows} row(s)" + (f", appended {appended}" if upsert else "") + f" in {props['title']}."
    if not_found:
        text += f" No row matched {key} = " + ", ".join(str(next(r[k] for k in r if k.lower() == key.lower())) for r in not_found) + "."
    return ({"updated": updated_rows, "appended": appended, "not_found": len(not_found)},
            {"updated": updated_rows, "appended": appended, "not_found": not_found}, text)


def update_rows(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Change the given columns of the rows whose key column matches; never appends."""
    return _update(ctx, p, upsert=False)


def upsert_rows(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Update the rows whose key column matches and append the others."""
    return _update(ctx, p, upsert=True)


def delete_rows(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    """Delete rows by row number, or the rows whose column equals a value."""
    sid, props, headers, existing = read_table(ctx, p)
    numbers: list[int] = []
    if p.get("row_numbers"):
        try:
            numbers = [int(n) for n in str(p["row_numbers"]).replace(" ", "").split(",") if n]
        except ValueError as e:
            raise GoogleAuthError("row_numbers must be comma-separated numbers, e.g. 4,7.") from e
        if any(n <= _header_row(p) for n in numbers):
            raise GoogleAuthError("row_numbers must be data rows, below the header row.")
    elif p.get("filter_column"):
        key = headers[_column_index(headers, str(p["filter_column"]))]
        numbers = [r["_row"] for r in existing if _matches(r, key, p.get("filter_value", ""))]
    else:
        raise GoogleAuthError("Give row_numbers, or filter_column and filter_value.")
    if not numbers:
        return {"deleted": 0}, {"deleted": 0}, "No rows matched; nothing was deleted."
    # Bottom-up, so earlier deletions do not shift the later rows.
    requests = [{"deleteDimension": {"range": {"sheetId": props["sheetId"], "dimension": "ROWS", "startIndex": n - 1, "endIndex": n}}}
                for n in sorted(set(numbers), reverse=True)]
    google_request(ctx, "POST", f"{API}/{segment(sid)}:batchUpdate", json_body={"requests": requests})
    return {"deleted": len(requests)}, {"deleted_rows": sorted(set(numbers))}, f"Deleted {len(requests)} row(s) from {props['title']}."


# ── ranges ───────────────────────────────────────────────────────────


def _a1(ctx: GoogleContext, sid: str, p: Mapping[str, Any]) -> str:
    """The A1 range: 'Sheet!A1:C9', a bare range on the given (or first) sheet, or the whole sheet."""
    rng = str(p.get("range") or "").strip()
    if "!" in rng:
        return rng
    title = sheet_props(ctx, sid, str(p.get("sheet") or "").strip() or None)["title"]
    return f"{quote_sheet(title)}!{rng}" if rng else quote_sheet(title)


def read_range(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    sid = spreadsheet_id(p)
    a1 = _a1(ctx, sid, p)
    values = get_values(ctx, sid, a1, str(p.get("value_render") or "FORMATTED_VALUE"))
    return ({"values": values, "rows": len(values)}, {"range": a1, "values": values},
            f"{a1}: {len(values)} row(s)\n" + "\n".join("\t".join(str(c) for c in row) for row in values[:100]))


def write_range(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    sid = spreadsheet_id(p)
    a1 = _a1(ctx, sid, p)
    raw = p.get("values")
    try:
        values = raw if isinstance(raw, list) else json.loads(str(raw or ""))
    except ValueError as e:
        raise GoogleAuthError(f'values must be a JSON array of rows, e.g. [["Name", "Score"], ["Kim", 90]]: {e}') from e
    if not isinstance(values, list) or not values or not all(isinstance(r, list) for r in values):
        raise GoogleAuthError('values must be a JSON array of rows, e.g. [["Name", "Score"], ["Kim", 90]].')
    result = json_of(google_request(ctx, "PUT", f"{API}/{segment(sid)}/values/{segment(a1)}", params={"valueInputOption": "USER_ENTERED"},
                                    json_body={"values": [[_cell(c) for c in row] for row in values]}))
    return ({"updated_cells": result.get("updatedCells", 0), "range": result.get("updatedRange", a1)}, result,
            f"Wrote {result.get('updatedCells', 0)} cell(s) to {result.get('updatedRange', a1)}.")


def clear_range(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    sid = spreadsheet_id(p)
    a1 = _a1(ctx, sid, p)
    result = json_of(google_request(ctx, "POST", f"{API}/{segment(sid)}/values/{segment(a1)}:clear", json_body={}))
    return {"range": result.get("clearedRange", a1)}, result, f"Cleared {result.get('clearedRange', a1)} (formatting kept)."
