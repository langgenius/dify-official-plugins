import oracledb
import csv
import io
from typing import Generator, Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class OracleDbPluginTool(Tool):
    def __init__(self, runtime=None, session=None):
        super().__init__(runtime, session)
        # Get current language environment, default to English
        self.language = self.get_language()
    
    def get_language(self):
        # Get language settings from runtime environment, default to 'en_US'
        try:
            # In actual applications, language settings may need to be obtained from different locations
            # This is just an example
            return 'en_US'
        except:
            return 'en_US'
    
    def get_message(self, messages_dict):
        # Return corresponding message based on current language, if no message for current language, return English message
        return messages_dict.get(self.language, messages_dict.get('en_US', ''))
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Or can also use Iterator[ToolInvokeMessage] if you don't need to specify send and return types
        # def _invoke(self, tool_parameters: dict[str, Any]) -> Iterator[ToolInvokeMessage]:
        conn = None
        try:
            # Get connection parameters
            host = tool_parameters.get('host')
            port = tool_parameters.get('port', 1521)  # Use default port 1521
            user = tool_parameters.get('user')
            password = tool_parameters.get('password')
            service_name = tool_parameters.get('service_name')
            sql_query = tool_parameters.get('query')
            output_format = tool_parameters.get('output_format', 'JSON')  # Default to JSON format
            
            # Validate required parameters
            if not all([host, user, password, service_name, sql_query]):
                messages = {
                    'en_US': 'Missing required parameters: host, user, password, service_name, query are all required',
                    'zh_Hans': '缺少必要参数：host、user、password、service_name、query都是必需的'
                }
                yield self.create_json_message({
                    "status": "error",
                    "message": self.get_message(messages)
                })
                return
            
            # python-oracledb uses Thin Mode by default, no additional configuration needed
            
            # Build connection string
            dsn = f'{host}:{port}/{service_name}'
            
            # Connect to database
            conn = oracledb.connect(
                user=user,
                password=password,
                dsn=dsn
            )
            
            # Create cursor
            with conn.cursor() as cursor:
                # Execute query
                cursor.execute(sql_query)
                
                # Get column names
                columns = [col[0] for col in cursor.description]
                
                # Get query results
                results = []
                for row in cursor.fetchall():
                    # Convert each row data to dictionary
                    row_dict = {columns[i]: value for i, value in enumerate(row)}
                    # Handle possible special types
                    for key, value in row_dict.items():
                        # Handle LOB type
                        if isinstance(value, oracledb.LOB):
                            try:
                                # Try to convert LOB to string
                                row_dict[key] = value.read()
                            except:
                                # If read fails, set to None or error message
                                row_dict[key] = None
                        # Convert datetime object to string
                        elif hasattr(value, 'strftime'):
                            row_dict[key] = value.strftime('%Y-%m-%d %H:%M:%S')
                    results.append(row_dict)
                
                # Format and return results based on output_format
                messages = {
                    'en_US': f'Query executed successfully, returned {len(results)} rows.',
                    'zh_Hans': f'查询执行成功，返回了{len(results)}行数据。'
                }
                
                if output_format == 'JSON':
                    # Return results in JSON format
                    yield self.create_json_message({
                        "status": "success",
                        "data": results,
                        "columns": columns,
                        "message": self.get_message(messages)
                    })
                elif output_format == 'Text-Markdown':
                    # Return results in Markdown table format
                    markdown_table = '| ' + ' | '.join(columns) + ' |\n'
                    markdown_table += '| ' + ' | '.join(['---'] * len(columns)) + ' |\n'
                    
                    for row in results:
                        row_values = []
                        for col in columns:
                            value = row.get(col, '')
                            row_values.append(str(value) if value is not None else '')
                        markdown_table += '| ' + ' | '.join(row_values) + ' |\n'
                    
                    yield self.create_text_message(f"{self.get_message(messages)}\n\n{markdown_table}")
                elif output_format == 'Text-CSV':
                    # Return results in CSV format, only return CSV content without message
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(results)
                    csv_content = output.getvalue()
                    
                    yield self.create_text_message(csv_content)
                else:
                    # Default to JSON if format is not recognized
                    yield self.create_json_message({
                        "status": "success",
                        "data": results,
                        "columns": columns,
                        "message": self.get_message(messages)
                    })
        except Exception as e:
            # Handle exceptions and return error message
            yield self.create_json_message({
                "status": "error",
                "message": str(e)
            })
        finally:
            # Ensure connection is closed
            if conn:
                try:
                    conn.close()
                except:
                    pass
