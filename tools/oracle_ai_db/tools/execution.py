import oracledb
from typing import Generator, Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class OracleDbExecutionTool(Tool):
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
        conn = None
        try:
            # Get connection parameters
            host = tool_parameters.get('host')
            port = tool_parameters.get('port', 1521)  # Use default port 1521
            user = tool_parameters.get('user')
            password = tool_parameters.get('password')
            service_name = tool_parameters.get('service_name')
            sql_statement = tool_parameters.get('statement')
            output_format = tool_parameters.get('output_format', 'JSON')  # Default to JSON format
            
            # Validate required parameters
            if not all([host, user, password, service_name, sql_statement]):
                messages = {
                    'en_US': 'Missing required parameters: host, user, password, service_name, statement are all required',
                    'zh_Hans': '缺少必要参数：host、user、password、service_name、statement都是必需的'
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
                # Execute SQL statement
                cursor.execute(sql_statement)
                
                # Commit transaction for DML statements
                conn.commit()
                
                # Get row count affected
                row_count = cursor.rowcount
                
                # Return results
                messages = {
                    'en_US': f'SQL statement executed successfully, affected {row_count} rows.',
                    'zh_Hans': f'SQL语句执行成功，影响了{row_count}行数据。'
                }
                
                if output_format == 'JSON':
                    # Return results in JSON format
                    yield self.create_json_message({
                        "status": "success",
                        "row_count": row_count,
                        "message": self.get_message(messages)
                    })
                elif output_format == 'Text-Markdown':
                    # Return results in Markdown format
                    markdown_content = f"## SQL Execution Result\n\n"
                    markdown_content += f"- **Status**: Success\n"
                    markdown_content += f"- **Affected Rows**: {row_count}\n"
                    yield self.create_text_message(markdown_content)
                elif output_format == 'Text-CSV':
                    # For execution tool, CSV format is not ideal but provide basic information
                    csv_content = f"status,row_count\nsuccess,{row_count}"
                    yield self.create_text_message(csv_content)
                else:
                    # Default to JSON if format is not recognized
                    yield self.create_json_message({
                        "status": "success",
                        "row_count": row_count,
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