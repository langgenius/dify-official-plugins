import json
from typing import Generator, Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from fish_audio_sdk import Session
import datetime

class ListModel(Tool):
        def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
            """
            List available models from Fish Audio
            """
            api_key = self.runtime.credentials.get("api_key")
            api_base = self.runtime.credentials.get("api_base")
            session = Session(api_key, base_url=api_base)
            param = {
                "page_size": tool_parameters.get("page_size", 10),
                "page_number": tool_parameters.get("page_number", 1),
                "self_only": tool_parameters.get("self_only", False),
                "sort_by": tool_parameters.get("sort_by", "task_count"),
            }
            if tool_parameters.get("title"):
                param["title"] = tool_parameters.get("title")
            if tool_parameters.get("tag"):
                param["tag"] = tool_parameters.get("tag")
            if tool_parameters.get("author_id"):
                param["author_id"] = tool_parameters.get("author_id")
            if tool_parameters.get("language"):
                param["language"] = tool_parameters.get("language")
            if tool_parameters.get("title_language"):
                param["title_language"] = tool_parameters.get("title_language")
            try:
                result = session.list_models(**param)
                items = result.items
                total = result.total
                page = param.get("page_number", 1)
                size = param.get("page_size", 10)
                if not items:
                    yield self.create_text_message("未找到任何模型。")
                else:
                    lines = [
                        f"📦 共找到 {total} 个模型，当前为第 {page} 页，每页 {size} 个。\n"
                    ]

                    for i, item in enumerate(items, start=1):
                        id = item.id  # 前提是你用 alias="_id" 做了映射
                        title = item.title or "无标题"
                        author = item.author.nickname if item.author else "匿名"
                        languages = ", ".join(item.languages) if item.languages else "未指定"
                        desc = item.description.strip() or "无描述"
                        visibility = item.visibility or "未知"

                        lines.append(
                            f"{i}. 【{title}】(ID: {id})\n"
                            f"    👤 作者：{author}\n"
                            f"    🌐 语言：{languages}\n"
                            f"    📝 描述：{desc}\n"
                            f"    🔒 可见性：{visibility}"
                        )

                    yield self.create_text_message("\n\n".join(lines))
                yield self.create_json_message(result.model_dump())

            except Exception as e:
                yield self.create_text_message(f"list model failed:{e}")

