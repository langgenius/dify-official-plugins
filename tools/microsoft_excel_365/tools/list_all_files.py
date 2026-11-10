from collections.abc import Generator
from typing import Any
from urllib.parse import quote

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, graph_request, segment
from tools.outputs import with_outputs

EXCEL_SUFFIXES = (".xlsx", ".xls", ".xlsm", ".xlsb")
_SELECT = "id,name,file,folder,size,createdDateTime,lastModifiedDateTime,webUrl,parentReference"


class ListAllFilesTool(Tool):
    """List files and folders in OneDrive (or a SharePoint site's library)"""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        folder_path = str(tool_parameters.get("folder_path") or "root").strip()
        file_type_filter = tool_parameters.get("file_type") or "all"
        max_results = int(tool_parameters.get("max_results") or 50)

        try:
            ctx = context_for(self, tool_parameters)
            if folder_path == "root":
                url = f"{ctx.drive_base}/root/children"
            elif folder_path == "recent":
                url = f"{ctx.drive_base}/recent"
            elif folder_path.startswith("id:"):
                url = f"{ctx.drive_base}/items/{segment(folder_path[3:])}/children"
            else:
                url = f"{ctx.drive_base}/root:/{quote(folder_path.strip('/'), safe='/')}:/children"
            data = graph_request(ctx, "GET", url, params={"$top": str(max_results), "$select": _SELECT}).json()
        except GraphAuthError as e:
            yield self.create_text_message(f"Failed to list files: {e}")
            return

        folders, excel_files, files = [], [], []
        for item in data.get("value", []):
            info = {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "type": "folder" if item.get("folder") else "file",
                "size": item.get("size", 0),
                "created_date": item.get("createdDateTime", ""),
                "modified_date": item.get("lastModifiedDateTime", ""),
                "web_url": item.get("webUrl", ""),
            }
            if item.get("folder"):
                info["child_count"] = item["folder"].get("childCount", 0)
                folders.append(info)
            elif info["name"].lower().endswith(EXCEL_SUFFIXES):
                info["file_type"] = "excel"
                excel_files.append(info)
            else:
                info["file_type"] = "other"
                files.append(info)

        items = {"excel": excel_files, "folders": folders}.get(file_type_filter, folders + excel_files + files)
        self._out.update(
            items=[
                {"id": i["id"], "name": i["name"], "type": i.get("file_type") or i["type"], "size": int(i["size"] or 0),
                 "modified_date": i["modified_date"], "web_url": i["web_url"]}
                for i in items
            ],
            count=len(items),
            success=True,
        )
        if not items:
            yield self.create_text_message(f"No items found in '{folder_path}'.")
            return

        yield self.create_json_message(
            {
                "items": items,
                "total_count": len(items),
                "folder_count": len(folders),
                "excel_count": len(excel_files),
                "other_file_count": len(files),
                "current_path": folder_path,
            }
        )
        summary = f"Found {len(items)} item(s) in '{folder_path}':\n\n"
        if folders and file_type_filter != "excel":
            summary += f"📁 Folders ({len(folders)}):\n"
            for folder in folders[:5]:
                summary += f"  - {folder['name']} ({folder['child_count']} items) [ID: {folder['id']}]\n"
            if len(folders) > 5:
                summary += f"  ... and {len(folders) - 5} more folders\n"
            summary += "\n"
        if excel_files and file_type_filter != "folders":
            summary += f"📊 Excel Files ({len(excel_files)}):\n"
            for excel in excel_files[:10]:
                summary += f"  - {excel['name']} ({excel['size'] / (1024 * 1024):.2f} MB) [ID: {excel['id']}]\n"
            if len(excel_files) > 10:
                summary += f"  ... and {len(excel_files) - 10} more Excel files\n"
            summary += "\n"
        if files and file_type_filter == "all":
            summary += f"📄 Other Files ({len(files)}):\n"
            for f in files[:5]:
                summary += f"  - {f['name']}\n"
            if len(files) > 5:
                summary += f"  ... and {len(files) - 5} more files\n"
        yield self.create_text_message(summary.rstrip())
