from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from neo4j_utils import Neo4jUtils


class ListGdsProceduresTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List available Graph Data Science (GDS) procedures in the Neo4j instance.
        """
        # Get parameters
        filter_text = tool_parameters.get("filter", "")

        try:
            # Get credentials
            uri = self.runtime.credentials.get("uri")
            username = self.runtime.credentials.get("username")
            password = self.runtime.credentials.get("password")

            if not uri or not username or not password:
                yield self.create_text_message("Neo4j credentials are not configured properly.")
                return

            # Get GDS procedures
            try:
                procedures = Neo4jUtils.list_gds_procedures(uri, username, password)

                if not procedures:
                    yield self.create_text_message(
                        "No GDS procedures found. The Graph Data Science library may not be installed "
                        "on this Neo4j instance. Visit https://neo4j.com/docs/graph-data-science/ "
                        "for installation instructions."
                    )
                    yield self.create_json_message({"procedures": [], "count": 0})
                    return

                # Apply filter if provided
                if filter_text:
                    filter_lower = filter_text.lower()
                    procedures = [
                        p for p in procedures
                        if filter_lower in p.get("name", "").lower()
                        or filter_lower in p.get("description", "").lower()
                    ]

                # Create summary message
                if not procedures:
                    summary = f"No GDS procedures found matching filter '{filter_text}'."
                elif len(procedures) == 1:
                    summary = "Found 1 GDS procedure"
                else:
                    summary = f"Found {len(procedures)} GDS procedures"

                if filter_text:
                    summary += f" matching '{filter_text}'"

                summary += "."

                # List procedure names in summary
                if procedures and len(procedures) <= 20:
                    procedure_names = [p.get("name", "Unknown") for p in procedures]
                    summary += "\n\nProcedures:\n- " + "\n- ".join(procedure_names)
                elif procedures:
                    # Only show first 20 if there are many
                    procedure_names = [p.get("name", "Unknown") for p in procedures[:20]]
                    summary += f"\n\nFirst 20 procedures:\n- " + "\n- ".join(procedure_names)
                    summary += f"\n\n... and {len(procedures) - 20} more."

                yield self.create_text_message(summary)
                yield self.create_json_message({
                    "count": len(procedures),
                    "filter": filter_text if filter_text else None,
                    "procedures": procedures
                })

            except Exception as e:
                yield self.create_text_message(f"Error listing GDS procedures: {str(e)}")
                return

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return
