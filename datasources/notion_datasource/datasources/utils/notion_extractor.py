from typing import Any

from datasources.utils.notion_client import NotionClient

# If user wants to split by headings, use the corresponding splitter
HEADING_SPLITTER = {
    "heading_1": "# ",
    "heading_2": "## ",
    "heading_3": "### ",
}


class NotionExtractor:
    def __init__(self, access_token: str, page_id: str, page_type: str, workspace_id: str):
        self._notion_access_token = access_token
        self._page_id = page_id
        self._page_type = page_type
        self._workspace_id = workspace_id
        self._client = NotionClient(self._notion_access_token)

    def extract(self) -> dict[str, Any]:
        """Main entry point for invoking the tool."""
        extractor_result = self._load_data_as_documents(self._page_id, self._page_type)
        return {
            "content": extractor_result,
            "workspace_id": self._workspace_id,
            "page_id": self._page_id,
        }

    def _load_data_as_documents(self, notion_obj_id: str, notion_obj_type: str) -> str:
        """Load data from Notion as documents."""
        if notion_obj_type == "database":
            extractor_result = self._get_notion_database_data(notion_obj_id)
        elif notion_obj_type == "page":
            extractor_result = self._get_notion_block_data(notion_obj_id)
        else:
            raise ValueError("Notion object type not supported")
        return extractor_result

    def _get_notion_database_data(self, database_id: str) -> str:
        """Fetch all pages from a Notion database and return as a Markdown table."""
        assert self._notion_access_token is not None, "Notion access token is required"

        # Retrieve database metadata
        database_data = self._client.retrieve_database(database_id=database_id)

        # Extract database title
        title = database_data.get("title", [])
        database_title = "".join([text.get("plain_text", "") for text in title]) if title else "Untitled Database"

        # Query database content
        data = self._client.query_database(database_id=database_id)

        # Check if the returned data is valid
        if "results" not in data or not data["results"]:
            return ""

        database_data["content"] = data["results"]

        # Initialize Markdown table
        markdown_table = [f"# {database_title}\n"]
        headers = []
        rows = []

        # Process each row in the database
        for result in data["results"]:
            properties = result["properties"]
            row_data = {}

            # Extract the header and corresponding values for each column
            for property_name, property_value in properties.items():
                row_data[property_name] = self._extract_property_value(property_value)

            # If it is the first row, extract the headers
            if not headers:
                headers = list(row_data.keys())

            # Add row data
            rows.append([row_data.get(header, "") for header in headers])

        # Build Markdown table
        markdown_table.append(self._generate_markdown_table(headers, rows))

        # Convert Markdown table to string
        markdown_content = "\n".join(markdown_table)

        return markdown_content

    def _get_notion_block_data(self, page_id: str) -> str:
        """Fetch and process Notion block data."""
        assert self._notion_access_token is not None, "Notion access token is required"
        result_lines_arr = []

        # Retrieve page metadata
        page_data = self._client.retrieve_page(page_id=page_id)
        page_data = self._format_page_data(page_data)
        title = page_data["title"]
        result_lines_arr.append(f"# {title}\n\n")

        # Retrieve block children
        data = self._paginate(self._client.retrieve_block_children, block_id=page_id)
        page_data["content"] = data

        for result in data:
            result_type = result["type"]
            result_obj = result[result_type]
            cur_result_text_arr = []

            if result_type == "table":
                result_block_id = result["id"]
                text = self._read_table_rows(result_block_id)
                result_lines_arr.append(text + "\n\n")
            else:
                if "rich_text" in result_obj:
                    for rich_text in result_obj["rich_text"]:
                        if "text" in rich_text:
                            text = rich_text["text"]["content"]
                            cur_result_text_arr.append(text)

                result_block_id = result["id"]
                has_children = result["has_children"]
                block_type = result["type"]
                if has_children and block_type != "child_page":
                    children_text = self._read_block(result_block_id, num_tabs=1)
                    cur_result_text_arr.append(children_text)

                cur_result_text = "\n".join(cur_result_text_arr)
                if result_type in HEADING_SPLITTER:
                    result_lines_arr.append(f"{HEADING_SPLITTER[result_type]}{cur_result_text}")
                else:
                    result_lines_arr.append(cur_result_text + "\n\n")

        md_content = "\n".join(result_lines_arr)
        return md_content

    def _read_block(self, block_id: str, num_tabs: int = 0) -> str:
        """Read a block and its children with caching."""
        data = self._paginate(self._client.retrieve_block_children, block_id=block_id)
        result_lines_arr = []

        for result in data:
            result_type = result["type"]
            result_obj = result[result_type]
            cur_result_text_arr = []

            if result_type == "table":
                result_block_id = result["id"]
                text = self._read_table_rows(result_block_id)
                result_lines_arr.append(text)
            else:
                if "rich_text" in result_obj:
                    for rich_text in result_obj["rich_text"]:
                        if "text" in rich_text:
                            text = rich_text["text"]["content"]
                            prefix = "\t" * num_tabs
                            cur_result_text_arr.append(prefix + text)

                result_block_id = result["id"]
                has_children = result["has_children"]
                block_type = result["type"]
                if has_children and block_type != "child_page":
                    children_text = self._read_block(result_block_id, num_tabs=num_tabs + 1)
                    cur_result_text_arr.append(children_text)

                cur_result_text = "\n".join(cur_result_text_arr)
                if result_type in HEADING_SPLITTER:
                    result_lines_arr.append(f"{HEADING_SPLITTER[result_type]}{cur_result_text}")
                else:
                    result_lines_arr.append(cur_result_text + "\n\n")

        return "\n".join(result_lines_arr)

    def _read_table_rows(self, block_id: str) -> str:
        """Read table rows and convert to Markdown."""
        data = self._paginate(self._client.retrieve_block_children, block_id=block_id)

        # Extract table headers
        table_header_cells = data[0]["table_row"]["cells"]
        headers = [self._extract_cell_text(cell) for cell in table_header_cells]

        # Process table rows
        rows = []
        for row in data[1:]:
            table_column_cells = row["table_row"]["cells"]
            rows.append([self._extract_cell_text(cell) for cell in table_column_cells])

        return self._generate_markdown_table(headers, rows)

    def _extract_property_value(self, property_value: dict) -> Any:
        """Extract the value of a Notion property."""
        column_type = property_value["type"]
        if column_type == "multi_select":
            return ", ".join(option["name"] for option in property_value[column_type])
        elif column_type in {"rich_text", "title"}:
            return property_value[column_type][0]["plain_text"] if property_value[column_type] else ""
        elif column_type in {"select", "status"}:
            return property_value[column_type]["name"] if property_value[column_type] else ""
        elif column_type == "number":
            return property_value.get("number")
        elif column_type == "date":
            date_data = property_value.get("date", {})
            return {"start": date_data.get("start"), "end": date_data.get("end")} if date_data else None
        elif column_type == "formula":
            formula_value = property_value[column_type]
            return (
                formula_value.get("number")
                if isinstance(formula_value, dict) and formula_value.get("type") == "number"
                else formula_value
            )
        elif column_type == "created_by":
            # Handle created_by type
            created_by_data = property_value.get("created_by", {})
            return created_by_data.get("name") if created_by_data else None
        else:
            return property_value[column_type]

    def _extract_cell_text(self, cell: list[dict]) -> str:
        """Extract text content from a table cell."""
        if not cell:
            return ""
        return " ".join(text["text"]["content"] for text in cell if "text" in text)

    def _generate_markdown_table(self, headers: list[str], rows: list[list[str]]) -> str:
        """Generate a Markdown table from headers and rows."""
        markdown = ["| " + " | ".join(headers) + " |"]
        markdown.append("| " + " | ".join(["---"] * len(headers)) + " |")
        for row in rows:
            markdown.append("| " + " | ".join(str(cell) if cell is not None else "" for cell in row) + " |")
        return "\n".join(markdown)

    def _paginate(self, fetch_function, **kwargs) -> list[dict]:
        """Handle pagination for Notion API requests."""
        results = []
        start_cursor = None
        while True:
            query_dict = kwargs.copy()
            if start_cursor:
                query_dict["start_cursor"] = start_cursor
            data = fetch_function(**query_dict)
            if "results" not in data or not data["results"]:
                break
            results.extend(data["results"])
            if data.get("next_cursor") is None:
                break
            start_cursor = data["next_cursor"]
        return results

    def _format_page_data(self, page_data: dict[str, Any]) -> dict[str, Any]:
        """Format the page data for the response."""
        result = {
            "id": page_data.get("id", ""),
            "created_time": page_data.get("created_time", ""),
            "last_edited_time": page_data.get("last_edited_time", ""),
            "archived": page_data.get("archived", False),
        }

        # Extract properties
        properties = page_data.get("properties", {})
        formatted_properties = {}

        title = "Untitled"
        for prop_name, prop_data in properties.items():
            prop_type = prop_data.get("type")

            # Extract value based on property type
            if prop_type == "title":
                title_content = prop_data.get("title", [])
                value = self._client.extract_plain_text(title_content)
                if value:
                    title = value  # Save title for the result
            elif prop_type == "rich_text":
                text_content = prop_data.get("rich_text", [])
                value = self._client.extract_plain_text(text_content)
            elif prop_type == "number":
                value = prop_data.get("number")
            elif prop_type == "select":
                select_data = prop_data.get("select", {})
                value = select_data.get("name") if select_data else None
            elif prop_type == "multi_select":
                multi_select = prop_data.get("multi_select", [])
                value = [item.get("name") for item in multi_select] if multi_select else []
            elif prop_type == "date":
                date_data = prop_data.get("date", {})
                start = date_data.get("start") if date_data else None
                end = date_data.get("end") if date_data else None
                value = {"start": start, "end": end} if start else None
            elif prop_type == "checkbox":
                value = prop_data.get("checkbox")
            elif prop_type == "url":
                value = prop_data.get("url")
            elif prop_type == "email":
                value = prop_data.get("email")
            elif prop_type == "phone_number":
                value = prop_data.get("phone_number")
            else:
                # For other property types, just note the type
                value = f"<{prop_type}>"

            formatted_properties[prop_name] = value

        result["title"] = title
        result["properties"] = formatted_properties
        return result
