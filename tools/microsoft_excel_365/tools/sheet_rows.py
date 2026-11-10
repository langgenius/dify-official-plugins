"""
Rows by header, for the row-based worksheet and table tools.

Agents and workflows think in rows such as {"Name": "Kim", "Score": 90}; Excel stores a grid.
These helpers read a sheet's used range, take its first row as the header, and turn
objects into rows of that width (and back).
"""

import json
from typing import Any

from tools.graph_client import GraphAuthError, GraphContext, column_letter, graph_request, top_left


def parse_records(value: Any, name: str = "rows") -> list[Any]:
    """A JSON array of rows: objects keyed by column header, or lists of cell values."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise GraphAuthError(f"{name} is required.")
        try:
            value = json.loads(text)
        except ValueError as e:
            raise GraphAuthError(f'{name} must be JSON, e.g. [{{"Name": "Kim", "Score": 90}}] or [["Kim", 90]].') from e
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list) or not value:
        raise GraphAuthError(f'{name} must be a non-empty JSON array, e.g. [{{"Name": "Kim", "Score": 90}}].')
    if all(isinstance(row, dict) for row in value) or all(isinstance(row, list) for row in value):
        return value
    if not any(isinstance(row, (dict, list)) for row in value):
        return [value]  # one flat row of cell values
    raise GraphAuthError(f"{name} must be all objects or all lists, not a mix.")


def rows_for_header(records: list[Any], header: list[str], name: str = "rows") -> list[list[Any]]:
    """Rows as lists in header order. Objects may leave columns out (empty); unknown keys are an error."""
    width = len(header)
    if records and isinstance(records[0], dict):
        known = {str(h): i for i, h in enumerate(header)}
        unknown = sorted({str(k) for row in records for k in row} - set(known))
        if unknown:
            raise GraphAuthError(f"{name} has keys that are not column headers: {', '.join(unknown)}. Headers: {', '.join(map(str, header))}.")
        out = []
        for row in records:
            cells: list[Any] = [""] * width
            for key, value in row.items():
                cells[known[str(key)]] = _cell(value)
            out.append(cells)
        return out
    rows = [[_cell(v) for v in row] for row in records]
    if any(len(row) != width for row in rows):
        raise GraphAuthError(f"Every row in {name} must have {width} cells, one per column: {', '.join(map(str, header))}.")
    return rows


def _cell(value: Any) -> Any:
    """Excel takes text, numbers and booleans; anything else is written as JSON text."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def as_records(header: list[Any], rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Rows as objects keyed by header."""
    keys = [str(h) if str(h) != "" else column_letter(i) for i, h in enumerate(header)]
    return [dict(zip(keys, row)) for row in rows]


class UsedRange:
    """A worksheet's used range: its header row, data rows and where it sits on the sheet."""

    def __init__(self, ctx: GraphContext, workbook_id: str, worksheet: str):
        data = graph_request(ctx, "GET", ctx.used_range(workbook_id, worksheet)).json()
        values = data.get("values") or []
        self.first_col, self.first_row = top_left(data.get("address") or "A1")
        # An empty sheet's used range is the single empty cell A1.
        self.empty = not values or all(str(c) == "" for row in values for c in row)
        self.header = [] if self.empty else list(values[0])
        self.rows = [] if self.empty else [list(r) for r in values[1:]]
        self.row_count = 0 if self.empty else len(values)

    def next_row(self) -> int:
        """Sheet row number just below the used range."""
        return self.first_row + self.row_count

    def address(self, row_number: int, width: int, height: int = 1) -> str:
        first = column_letter(self.first_col)
        last = column_letter(self.first_col + width - 1)
        return f"{first}{row_number}:{last}{row_number + height - 1}"


def match_and_write(
    ctx: GraphContext,
    workbook_id: str,
    worksheet: str,
    key_column: str,
    records: list[Any],
    *,
    update_all: bool,
    append: bool,
) -> tuple[int, list[str], list[str]]:
    """
    Write each record (an object keyed by header) into the rows whose key column matches it;
    columns left out of a record keep their value. Only the first match is updated unless
    ``update_all``. Records with no match are appended below the data when ``append``,
    otherwise reported. Returns (rows updated, keys appended, keys not found).
    """
    if not records or not isinstance(records[0], dict):
        raise GraphAuthError('rows must be objects keyed by column header, e.g. [{"ID": "42", "Status": "Done"}].')
    used = UsedRange(ctx, workbook_id, worksheet)
    if used.empty:
        raise GraphAuthError(f"'{worksheet}' has no header row and no data to match.")
    header = [str(h) for h in used.header]
    if key_column not in header:
        raise GraphAuthError(f"'{key_column}' is not a column header. Headers: {', '.join(header)}.")
    key_at = header.index(key_column)
    if any(str(r.get(key_column, "")).strip() == "" for r in records):
        raise GraphAuthError(f"Every row needs a value for the key column '{key_column}'.")
    rows_for_header(records, header)  # rejects keys that are not headers

    # Sheet row numbers of each key, in sheet order, and the current cells of every data row.
    where: dict[str, list[int]] = {}
    current: dict[int, list[Any]] = {}
    for i, row in enumerate(used.rows):
        number = used.first_row + 1 + i
        current[number] = list(row) + [""] * (len(header) - len(row))
        where.setdefault(str(row[key_at]) if key_at < len(row) else "", []).append(number)

    updated, appended, missing = 0, [], []
    next_row = used.next_row()
    for record in records:
        key = str(record[key_column])
        targets = where.get(key, [])
        if not update_all:
            targets = targets[:1]
        if not targets:
            if not append:
                missing.append(key)
                continue
            targets = [next_row]
            where[key] = [next_row]
            current[next_row] = [""] * len(header)
            next_row += 1
            appended.append(key)
        else:
            updated += len(targets)
        values = rows_for_header([record], header)[0]
        for number in targets:
            cells = current[number]
            for col, name in enumerate(header):
                if name in record:
                    cells[col] = values[col]
            graph_request(
                ctx, "PATCH", ctx.range(workbook_id, worksheet, used.address(number, len(header))), json_body={"values": [cells]}
            )
    return updated, appended, missing
