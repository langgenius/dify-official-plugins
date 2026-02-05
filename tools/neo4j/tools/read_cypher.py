from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from neo4j_utils import Neo4jUtils


class ReadCypherTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Execute a read-only Cypher query on Neo4j.
        """
        # Get parameters
        query = tool_parameters.get("query", "")
        limit = tool_parameters.get("limit", 100)

        # Validate query
        if not query:
            yield self.create_text_message("Cypher query is required.")
            return

        # Check if query is read-only
        if not Neo4jUtils.is_read_only_query(query):
            yield self.create_text_message(
                "This tool only accepts read-only queries. "
                "Write operations (CREATE, MERGE, SET, DELETE, REMOVE, DROP) are not allowed. "
                "Please use the 'Write Cypher Query' tool for write operations."
            )
            return

        try:
            # Get credentials
            uri = self.runtime.credentials.get("uri")
            username = self.runtime.credentials.get("username")
            password = self.runtime.credentials.get("password")

            if not uri or not username or not password:
                yield self.create_text_message("Neo4j credentials are not configured properly.")
                return

            # Add LIMIT clause if not present and limit is specified
            query_upper = query.upper().strip()
            if limit and "LIMIT" not in query_upper:
                # Find the position to insert LIMIT (after RETURN clause, before any ORDER BY if present)
                if not query.strip().endswith(";"):
                    query = f"{query} LIMIT {int(limit)}"
                else:
                    query = f"{query[:-1]} LIMIT {int(limit)};"

            # Execute query
            try:
                results = Neo4jUtils.execute_read_cypher(uri, username, password, query)

                # Create summary message
                result_count = len(results)
                if result_count == 0:
                    summary = "Query executed successfully. No results found."
                elif result_count == 1:
                    summary = "Query executed successfully. 1 result returned."
                else:
                    summary = f"Query executed successfully. {result_count} results returned."

                if limit and result_count >= int(limit):
                    summary += f" (Limited to {int(limit)} results)"

                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "query": query,
                    "result_count": result_count,
                    "results": results
                })

            except Exception as e:
                error_message = str(e)
                if "syntax" in error_message.lower():
                    yield self.create_text_message(f"Cypher syntax error: {error_message}")
                else:
                    yield self.create_text_message(f"Error executing query: {error_message}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
