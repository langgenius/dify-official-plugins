from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from neo4j_utils import Neo4jUtils


class WriteCypherTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Execute a write Cypher query on Neo4j.
        """
        # Get parameters
        query = tool_parameters.get("query", "")

        # Validate query
        if not query:
            yield self.create_text_message("Cypher query is required.")
            return

        try:
            # Get credentials
            uri = self.runtime.credentials.get("uri")
            username = self.runtime.credentials.get("username")
            password = self.runtime.credentials.get("password")

            if not uri or not username or not password:
                yield self.create_text_message("Neo4j credentials are not configured properly.")
                return

            # Execute query
            try:
                result = Neo4jUtils.execute_write_cypher(uri, username, password, query)

                # Create summary message from statistics
                stats = result["statistics"]
                summary_parts = []

                if stats["nodes_created"] > 0:
                    summary_parts.append(f"{stats['nodes_created']} node(s) created")
                if stats["nodes_deleted"] > 0:
                    summary_parts.append(f"{stats['nodes_deleted']} node(s) deleted")
                if stats["relationships_created"] > 0:
                    summary_parts.append(f"{stats['relationships_created']} relationship(s) created")
                if stats["relationships_deleted"] > 0:
                    summary_parts.append(f"{stats['relationships_deleted']} relationship(s) deleted")
                if stats["properties_set"] > 0:
                    summary_parts.append(f"{stats['properties_set']} property(ies) set")
                if stats["labels_added"] > 0:
                    summary_parts.append(f"{stats['labels_added']} label(s) added")
                if stats["labels_removed"] > 0:
                    summary_parts.append(f"{stats['labels_removed']} label(s) removed")
                if stats["indexes_added"] > 0:
                    summary_parts.append(f"{stats['indexes_added']} index(es) added")
                if stats["indexes_removed"] > 0:
                    summary_parts.append(f"{stats['indexes_removed']} index(es) removed")
                if stats["constraints_added"] > 0:
                    summary_parts.append(f"{stats['constraints_added']} constraint(s) added")
                if stats["constraints_removed"] > 0:
                    summary_parts.append(f"{stats['constraints_removed']} constraint(s) removed")

                if summary_parts:
                    summary = "Query executed successfully. " + ", ".join(summary_parts) + "."
                else:
                    summary = "Query executed successfully. No modifications were made."

                data = result["data"]
                if data:
                    summary += f" {len(data)} result(s) returned."

                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "query": query,
                    "statistics": stats,
                    "data": data
                })

            except Exception as e:
                error_message = str(e)
                if "syntax" in error_message.lower():
                    yield self.create_text_message(f"Cypher syntax error: {error_message}")
                elif "constraint" in error_message.lower():
                    yield self.create_text_message(f"Constraint violation: {error_message}")
                else:
                    yield self.create_text_message(f"Error executing query: {error_message}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
