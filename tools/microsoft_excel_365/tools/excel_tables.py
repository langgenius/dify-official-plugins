"""
Shared reads for the Excel table tools (excel_*table* files: Table > Add, Delete,
Convert to Range, Get Columns, Get Rows, Append, Lookup, plus List Tables).

A table is named by its ID or its name (e.g. "Table1"); rows are returned as objects keyed
by the table's column names.
"""

from typing import Any

from tools.graph_client import GraphContext, graph_request

# Lookup reads at most this many rows.
_LOOKUP_MAX_ROWS = 5000


def table_header(ctx: GraphContext, workbook_id: str, table: str) -> list[str]:
    columns = graph_request(ctx, "GET", f"{ctx.table(workbook_id, table)}/columns", params={"$select": "name,index"}).json()
    return [str(c.get("name", "")) for c in sorted(columns.get("value", []), key=lambda c: c.get("index", 0))]


def table_rows(ctx: GraphContext, workbook_id: str, table: str, limit: int) -> tuple[list[list[Any]], bool]:
    """Up to ``limit`` data rows (as cell lists), and whether there are more."""
    rows: list[list[Any]] = []
    page = min(limit + 1, 500)
    skip = 0
    while len(rows) <= limit:
        body = graph_request(
            ctx, "GET", f"{ctx.table(workbook_id, table)}/rows", params={"$top": page, "$skip": skip, "$select": "index,values"}
        ).json()
        batch = [(r.get("values") or [[]])[0] for r in body.get("value", [])]
        rows.extend(batch)
        if len(batch) < page:
            break
        skip += len(batch)
    return rows[:limit], len(rows) > limit
