from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from neo4j_utils import Neo4jUtils


class GetSchemaTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get the Neo4j database schema including labels, relationship types, and property keys.
        """
        try:
            # Get credentials
            uri = self.runtime.credentials.get("uri")
            username = self.runtime.credentials.get("username")
            password = self.runtime.credentials.get("password")

            if not uri or not username or not password:
                yield self.create_text_message("Neo4j credentials are not configured properly.")
                return

            # Get schema
            try:
                schema = Neo4jUtils.get_schema(uri, username, password)

                # Create summary message
                summary_parts = []
                if schema["labels"]:
                    summary_parts.append(f"Node Labels ({len(schema['labels'])}): {', '.join(schema['labels'])}")
                else:
                    summary_parts.append("Node Labels: None found")

                if schema["relationship_types"]:
                    summary_parts.append(
                        f"Relationship Types ({len(schema['relationship_types'])}): {', '.join(schema['relationship_types'])}"
                    )
                else:
                    summary_parts.append("Relationship Types: None found")

                if schema["property_keys"]:
                    summary_parts.append(
                        f"Property Keys ({len(schema['property_keys'])}): {', '.join(schema['property_keys'])}"
                    )
                else:
                    summary_parts.append("Property Keys: None found")

                if schema["indexes"]:
                    summary_parts.append(f"Indexes: {len(schema['indexes'])} found")

                if schema["constraints"]:
                    summary_parts.append(f"Constraints: {len(schema['constraints'])} found")

                summary = "Database Schema:\n" + "\n".join(summary_parts)

                yield self.create_text_message(summary)
                yield self.create_json_message(schema)

            except Exception as e:
                yield self.create_text_message(f"Error retrieving schema: {str(e)}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
