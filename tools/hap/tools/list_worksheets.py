from collections.abc import Generator
from typing import Any
import json
import httpx
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class ListWorksheetsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        appkey = tool_parameters.get('appkey', '')
        if not appkey:
            yield self.create_json_message({'error': 'Invalid parameter App Key'})
            return
        sign = tool_parameters.get('sign', '')
        if not sign:
            yield self.create_json_message({'error': 'Invalid parameter Sign'})
            return
        
        host = tool_parameters.get('host', '')
        if not host:
            host = 'https://api.mingdao.com'
        elif not (host.startswith("http://") or host.startswith("https://")):
            yield self.create_json_message({'error': 'Invalid parameter Host Address'})
            return
        else:
            host = f"{host[:-1] if host.endswith('/') else host}/api"
        url = f"{host}/v1/open/app/get"

        result_type = tool_parameters.get('result_type', '')
        if not result_type:
            result_type = 'table'

        headers = { 'Content-Type': 'application/json' }
        params = { "appKey": appkey, "sign": sign, }
        try:
            res = httpx.get(url, headers=headers, params=params, timeout=30)
            res_json = res.json()
            if res.is_success:
                if res_json.get('error_code') != 1:
                    error_msg = res_json.get('error_msg', 'Unknown error')
                    yield self.create_json_message({'error': f"Failed to access the application. {error_msg}"})
                else:
                    data = res_json.get('data', {})
                    sections = data.get('sections', [])
                    if result_type == 'json':
                        worksheets = []
                        for section in sections:
                            worksheets.extend(self._extract_worksheets(section, result_type, depth=0))
                        yield self.create_json_message({'result': worksheets})
                    else:
                        worksheets = '|worksheetId|worksheetName|description|\n|---|---|---|'
                        for section in sections:
                            worksheets += self._extract_worksheets(section, result_type, depth=0)
                        yield self.create_json_message({'result': worksheets})
            else:
                yield self.create_json_message({'error': f"Failed to list worksheets, status code: {res.status_code}, response: {res.text}"})
        except Exception as e:
            error_msg = f"Failed to list worksheets, something went wrong: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})

    def _extract_worksheets(self, section, type, depth=0):
        # 防止无限递归
        if depth > 10:
            return [] if type == 'json' else ''
            
        items = []
        tables = ''
        
        for item in section.get('items', []):
            item_type = item.get('type')
            item_notes = item.get('notes', '')
            
            # 修复 notes 检查逻辑：只有当 notes 存在且等于 'NO' 时才跳过
            if item_type == 0 and item_notes != 'NO':
                if type == 'json':
                    item_id = item.get('id', '')
                    item_name = item.get('name', '')
                    if item_id and item_name:  # 只添加有效的项目
                        filtered_item = {
                            'id': item_id,
                            'name': item_name,
                            'notes': item_notes
                        }
                        items.append(filtered_item)
                else:
                    item_id = item.get('id', '')
                    item_name = item.get('name', '')
                    if item_id and item_name:  # 只添加有效的项目
                        # 安全处理字符串，避免特殊字符问题
                        safe_id = self.safe_string(item_id)
                        safe_name = self.safe_string(item_name)
                        safe_notes = self.safe_string(item_notes)
                        tables += f"\n|{safe_id}|{safe_name}|{safe_notes}|"

        # 递归处理子节点
        for child_section in section.get('childSections', []):
            if type == 'json':
                child_items = self._extract_worksheets(child_section, 'json', depth + 1)
                items.extend(child_items)
            else:
                child_tables = self._extract_worksheets(child_section, 'table', depth + 1)
                tables += child_tables
        
        return items if type == 'json' else tables
    
    def safe_string(self, text):
        """安全处理字符串，避免特殊字符问题"""
        if text is None:
            return ''
        text = str(text)
        # 替换可能破坏表格格式的字符
        text = text.replace('|', '▏').replace('\n', ' ').replace('\r', ' ')
        return text.strip()