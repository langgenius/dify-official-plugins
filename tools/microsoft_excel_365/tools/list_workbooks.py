from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, odata_string, segment
from tools.list_all_files import EXCEL_SUFFIXES
from tools.outputs import with_outputs

_SELECT = "id,name,file,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference"


def _workbook(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "size": item.get("size", 0),
        "created_date": item.get("createdDateTime", ""),
        "modified_date": item.get("lastModifiedDateTime", ""),
        "web_url": item.get("webUrl", ""),
        "path": (item.get("parentReference") or {}).get("path", ""),
    }


def _is_workbook(item: dict[str, Any]) -> bool:
    return bool(item.get("file")) and str(item.get("name", "")).lower().endswith(EXCEL_SUFFIXES)


class ListWorkbooksTool(Tool):
    """List Excel workbooks"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        folder_id = str(tool_parameters.get("folder_id") or "").strip()
        search_query = str(tool_parameters.get("search_query") or "").strip()
        max_results = int(tool_parameters.get("max_results") or 20)

        try:
            ctx = context_for(self, tool_parameters)
            if search_query:
                url, params = f"{ctx.drive_base}/root/search(q={odata_string(search_query)})", {"$top": str(max_results)}
            elif folder_id:
                url, params = f"{ctx.drive_base}/items/{segment(folder_id)}/children", {"$top": str(max_results), "$select": _SELECT}
            else:
                # Recently used files first.
                url, params = f"{ctx.drive_base}/recent", {"$top": str(max_results)}
            try:
                items = graph_request(ctx, "GET", url, params=params).json().get("value", [])
            except GraphAuthError:
                if search_query or folder_id:
                    raise
                items = []  # /recent is not available for every drive (e.g. app-only access)
            workbooks = [_workbook(item) for item in items if _is_workbook(item)]
            if not workbooks and not search_query and not folder_id:
                # Nothing recent: look in the root folder.
                items = graph_request(
                    ctx, "GET", f"{ctx.drive_base}/root/children", params={"$top": str(max_results), "$select": _SELECT}
                ).json().get("value", [])
                workbooks = [_workbook(item) for item in items if _is_workbook(item)]
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to list workbooks: {e}")
            return

        self._out.update(
            workbooks=[{"id": w["id"], "name": w["name"], "size": int(w["size"] or 0), "modified_date": w["modified_date"],
                        "web_url": w["web_url"], "path": w["path"]} for w in workbooks],
            count=len(workbooks),
            success=True,
        )
        if not workbooks:
            if search_query:
                yield self.create_text_message(f"No Excel workbooks found matching '{search_query}'.")
            elif folder_id:
                yield self.create_text_message("No Excel workbooks found in the specified folder.")
            else:
                yield self.create_text_message("No Excel workbooks found. Try uploading an Excel file to OneDrive first.")
            return
        yield self.create_json_message({"workbooks": workbooks, "count": len(workbooks)})
        yield self.create_text_message(
            f"Found {len(workbooks)} Excel workbook(s):\n" + "".join(f"- {w['name']} (ID: {w['id']})\n" for w in workbooks)
        )
