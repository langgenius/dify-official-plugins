import logging
from typing import Any, Generator

import sqlparse
import tabulate
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.db_util import DbUtil


class SqlQueryTool(Tool):
    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        print(tool_parameters)
        db_type = tool_parameters.get("db_type", "")
        if not db_type:
            raise ValueError("Please select the database type")
        db_host = tool_parameters.get("db_host", "")
        if not db_host:
            raise ValueError("Please fill in the database host")
        db_port = tool_parameters.get("db_port", "")
        if db_port is not None:
            db_port = str(db_port)
        db_username = tool_parameters.get("db_username", "")
        if not db_username:
            raise ValueError("Please fill in the database username")
        db_password = tool_parameters.get("db_password", "")
        if not db_password:
            raise ValueError("Please fill in the database password")
        db_name = tool_parameters.get("db_name", "")
        db_properties = tool_parameters.get("db_properties", "")

        query_sql = tool_parameters.get("query_sql", "")
        if not query_sql:
            raise ValueError("Please fill in the query SQL, for example: select * from tbl_name")
        statements = sqlparse.parse(query_sql)
        if len(statements) != 1:
            raise ValueError("Only a single query SQL can be filled")
        statement = statements[0]
        if statement.get_type() != 'SELECT':
            raise ValueError("Query SQL can only be a single SELECT statement")

        try:
            db = DbUtil(db_type=db_type,
                        username=db_username, password=db_password,
                        host=db_host, port=db_port,
                        database=db_name, properties=db_properties)
        except Exception as e:
            message = "Database connection creation exception."
            logging.exception(message)
            raise Exception(message + " {}".format(e))

        try:
            records = db.run_query(query_sql)
            text = tabulate.tabulate(records, headers="keys", tablefmt="github")
            yield self.create_text_message(text)
        except Exception as e:
            message = "SQL query execution exception."
            logging.exception(message)
            raise Exception(message + " {}".format(e))
