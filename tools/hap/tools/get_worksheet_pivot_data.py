from collections.abc import Generator
from typing import Any
import json
import httpx
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class GetWorksheetPivotDataTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        appkey = tool_parameters.get('appkey', '')
        if not appkey:
            yield self.create_json_message({'error': 'Invalid parameter App Key'})
            return
        sign = tool_parameters.get('sign', '')
        if not sign:
            yield self.create_json_message({'error': 'Invalid parameter Sign'})
            return
        worksheet_id = tool_parameters.get('worksheet_id', '')
        if not worksheet_id:
            yield self.create_json_message({'error': 'Invalid parameter Worksheet ID'})
            return
        x_column_fields = tool_parameters.get('x_column_fields', '')
        if not x_column_fields or not x_column_fields.startswith('['):
            yield self.create_json_message({'error': 'Invalid parameter Column Fields'})
            return
        y_row_fields = tool_parameters.get('y_row_fields', '')
        if y_row_fields and not y_row_fields.strip().startswith('['):
            yield self.create_json_message({'error': 'Invalid parameter Row Fields'})
            return
        elif not y_row_fields:
            y_row_fields = '[]'
        value_fields = tool_parameters.get('value_fields', '')
        if not value_fields or not value_fields.strip().startswith('['):
            yield self.create_json_message({'error': 'Invalid parameter Value Fields'})
            return
        filters = tool_parameters.get('filters', '')
        if filters and not filters.strip().startswith('['):
            yield self.create_json_message({'error': 'Invalid parameter Filters'})
            return
        elif not filters:
            filters = '[]'
        
        host = tool_parameters.get('host', '')
        if not host:
            host = 'https://api.mingdao.com'
        elif not host.startswith(("http://", "https://")):
            yield self.create_json_message({'error': 'Invalid parameter Host Address'})
            return
        else:
            host = f"{host[:-1] if host.endswith('/') else host}/api"

        url = f"{host}/report/getPivotData"
        headers = {'Content-Type': 'application/json'}
        payload = {"appKey": appkey, "sign": sign, "worksheetId": worksheet_id, "options": {"showTotal": True}}

        try:
            x_column_fields = json.loads(x_column_fields)
            payload['columns'] = x_column_fields
            y_row_fields = json.loads(y_row_fields)
            if y_row_fields: payload['rows'] = y_row_fields
            value_fields = json.loads(value_fields)
            payload['values'] = value_fields
            filters_parsed = json.loads(filters)
            if filters_parsed: payload['filters'] = filters_parsed
            sort_fields = tool_parameters.get('sort_fields', '')
            if not sort_fields: sort_fields = '[]'
            sort_fields = json.loads(sort_fields)
            if sort_fields: payload['options']['sort'] = sort_fields
            
            res = httpx.post(url, headers=headers, json=payload, timeout=60)
            res.raise_for_status()
            res_json = res.json()
            
            if res_json.get('status') != 1:
                yield self.create_json_message({'error': f"Failed to get the worksheet pivot data. {res_json['msg']}"})
            else:
                data = res_json.get('data')
                if data is None:
                    yield self.create_json_message({'error': 'No data returned from the API'})
                    return
                pivot_json = self.generate_pivot_json(data)
                pivot_table = self.generate_pivot_table(data)
                result_type = tool_parameters.get('result_type', '')
                if result_type == 'table':
                    yield self.create_json_message({'result': pivot_table})
                else:
                    yield self.create_json_message({'result': pivot_json})
        except httpx.RequestError as e:
            error_msg = f"Failed to get the worksheet pivot data, request error: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse JSON response: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})
        except Exception as e:
            error_msg = f"Failed to get the worksheet pivot data, unexpected error: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})

    def generate_pivot_table(self, data: dict[str, Any]) -> str:
        if data is None:
            return "|No data available|"
        
        metadata = data.get('metadata', {})
        if metadata is None:
            metadata = {}
        
        columns = metadata.get('columns', [])
        if columns is None:
            columns = []
        
        rows = metadata.get('rows', [])
        if rows is None:
            rows = []
        
        values = metadata.get('values', [])
        if values is None:
            values = []

        rows_data = data.get('data', [])
        if rows_data is None:
            rows_data = []

        header = ([row.get('displayName', '') for row in rows] if rows else []) + [column.get('displayName', '') for column in columns] + [value.get('displayName', '') for value in values]
        line = (['---'] * len(rows) if rows else []) + ['---'] * len(columns) + ['--:'] * len(values)

        table = [header, line]
        for row in rows_data:
            row_data = []
            if rows:
                for r in rows:
                    key = r.get('controlId', '') + ('-' + str(r.get('particleSize', '')) if r.get('particleSize') else '')
                    value = row.get('rows', {}).get(key, '')
                    row_data.append(self.replace_pipe(str(value)))
            
            for c in columns:
                key = c.get('controlId', '') + ('-' + str(c.get('particleSize', '')) if c.get('particleSize') else '')
                value = row.get('columns', {}).get(key, '')
                row_data.append(self.replace_pipe(str(value)))
            
            for v in values:
                key = v.get('controlId', '')
                value = row.get('values', {}).get(key, '')
                row_data.append(self.replace_pipe(str(value)))
            
            table.append(row_data)

        return '\n'.join([('|'+'|'.join(row) +'|') for row in table])
    
    def replace_pipe(self, text: str) -> str:
        if text is None:
            return ''
        return str(text).replace('|', '▏').replace('\n', ' ')
    
    def generate_pivot_json(self, data: dict[str, Any]) -> dict:
        if data is None:
            return {"fields": {"x-axis": [], "y-axis": [], "values": []}, "rows": [], "summary": {}}
        
        metadata = data.get('metadata', {})
        if metadata is None:
            metadata = {}
        
        columns = metadata.get("columns", [])
        if columns is None:
            columns = []
        
        rows = metadata.get("rows", [])
        if rows is None:
            rows = []
        
        values = metadata.get("values", [])
        if values is None:
            values = []
        
        fields = {
            "x-axis": [
                {"fieldId": column.get("controlId", ""), "fieldName": column.get("displayName", "")}
                for column in columns
            ],
            "y-axis": [
                {"fieldId": row.get("controlId", ""), "fieldName": row.get("displayName", "")}
                for row in rows
            ],
            "values": [
                {"fieldId": value.get("controlId", ""), "fieldName": value.get("displayName", "")}
                for value in values
            ]
        }
        rows_data = []
        data_rows = data.get("data", [])
        if data_rows is None:
            data_rows = []
        for row in data_rows:
            row_data = row.get("rows", {}) if row.get("rows") else {}
            row_data.update(row.get("columns", {}))
            row_data.update(row.get("values", {}))
            rows_data.append(row_data)
        return {"fields": fields, "rows": rows_data, "summary": metadata.get("totalRow", {})}
