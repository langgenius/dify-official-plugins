from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.graph_client import GraphAuthError, context_for, file_dict, get_all, resolve_site
from tools.outputs import with_outputs


class ListFilesTool(Tool):
    """Files and folders in a folder of the site's document library (n8n's folder and file pickers)."""

    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        folder_id = str(tool_parameters.get("folder_id") or "").strip()
        try:
            limit = max(1, min(int(tool_parameters.get("limit") or 100), 1000))
            ctx = context_for(self, tool_parameters)
            site = resolve_site(ctx, tool_parameters.get("site"))
            files = [file_dict(f) for f in get_all(ctx, f"{ctx.drive_item(site['site_id'], folder_id)}/children", {"$top": min(limit, 200)}, limit)]
        except (GraphAuthError, ValueError) as e:
            yield self.create_text_message(f"Failed to list the files: {e}")
            return
        self._out.update(files=files, count=len(files), success=True)
        where = f"folder {folder_id}" if folder_id and folder_id != "root" else f"the '{site['name']}' document library"
        yield self.create_text_message(
            f"{len(files)} item(s) in {where}:\n"
            + "\n".join(f"- {f['name']} ({'folder' if f['is_folder'] else f'{f['size']} bytes'}, id: {f['id']})" for f in files)
        )
        yield self.create_json_message({"files": files, "count": len(files)})
