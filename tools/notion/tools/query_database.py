from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.notion_client import NotionClient
from tools.notion_filters import (
    NO_VALUE_CONDITIONS,
    InvalidFilterConditionError,
    build_filter,
    extract_person,
    to_bool,
)

# Safety cap on Notion API calls when fetch_all paginates through a data source
# (mirrors retrieve_page.py's max_api_calls budget).
DEFAULT_MAX_API_CALLS = 500


class QueryDatabaseTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Extract parameters
        database_id = tool_parameters.get("database_id", "")
        filter_property = tool_parameters.get("filter_property", "")
        filter_value = tool_parameters.get("filter_value", "")
        limit = int(tool_parameters.get("limit", 10))
        fetch_all = to_bool(tool_parameters.get("fetch_all", False))
        max_api_calls = int(tool_parameters.get("max_api_calls") or DEFAULT_MAX_API_CALLS)
        if max_api_calls < 1:
            max_api_calls = 1

        # Validate parameters
        if not database_id:
            yield self.create_text_message("Database ID is required.")
            return

        try:
            # Get integration token from credentials
            integration_token = self.runtime.credentials.get("integration_token")
            if not integration_token:
                yield self.create_text_message("Notion Integration Token is required.")
                return

            # Initialize the Notion client
            client = NotionClient(integration_token)

            # Resolve the data source once; reused for schema lookup, filtering, and querying
            try:
                data_source_id = client.get_default_data_source_id(database_id)
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Database not found or you don't have access to it: {database_id}")
                else:
                    yield self.create_text_message(f"Error querying database: {e}")
                return
            except ValueError as e:
                yield self.create_text_message(str(e))
                return

            # Prepare filter if a property is provided (value is optional for is_empty/is_not_empty/relative-date conditions)
            filter_condition = tool_parameters.get("filter_condition", "equals")
            filter_obj = None
            if filter_property and (filter_value or filter_condition in NO_VALUE_CONDITIONS):
                # Get database schema to determine the property type
                try:
                    data_source = client.retrieve_data_source(data_source_id)
                    properties = data_source.get("properties", {})

                    # Find the property type (and its schema data, needed for rollup)
                    property_type = None
                    prop_data = {}
                    for prop_name, p_data in properties.items():
                        if prop_name == filter_property:
                            property_type = p_data.get("type")
                            prop_data = p_data
                            break

                    filter_obj = build_filter(filter_property, filter_condition, filter_value, property_type, prop_data)
                except InvalidFilterConditionError as e:
                    yield self.create_text_message(str(e))
                    return
                except Exception:
                    filter_obj = client.create_simple_text_filter(filter_property, filter_value)
            
            # Query the database
            truncated = False
            try:
                if fetch_all:
                    results = []
                    start_cursor = None
                    api_calls_made = 0
                    while True:
                        if api_calls_made >= max_api_calls:
                            truncated = True
                            break
                        data = client.query_data_source(
                            data_source_id=data_source_id,
                            filter_obj=filter_obj,
                            page_size=100,
                            start_cursor=start_cursor
                        )
                        api_calls_made += 1
                        results.extend(data.get("results", []))
                        if not data.get("has_more"):
                            break
                        start_cursor = data.get("next_cursor")
                        if not start_cursor:
                            break
                else:
                    data = client.query_data_source(
                        data_source_id=data_source_id,
                        filter_obj=filter_obj,
                        page_size=limit
                    )
                    results = data.get("results", [])
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    yield self.create_text_message(f"Database not found or you don't have access to it: {database_id}")
                else:
                    yield self.create_text_message(f"Error querying database: {e}")
                return
                
            if not results:
                filter_msg = f" with filter {filter_property}={filter_value}" if filter_property and filter_value else ""
                yield self.create_text_message(f"No results found in database{filter_msg}")
                return
                
            # Format results to extract and simplify property values
            formatted_results = []
            for result in results:
                # Get page ID and URL
                page_id = result.get("id")
                page_url = client.format_page_url(page_id)
                
                # Extract properties
                properties = result.get("properties", {})
                formatted_properties = {}
                
                for prop_name, prop_data in properties.items():
                    prop_type = prop_data.get("type")
                    
                    # Extract value based on property type
                    if prop_type == "title":
                        title_content = prop_data.get("title", [])
                        value = client.extract_plain_text(title_content)
                    elif prop_type == "rich_text":
                        text_content = prop_data.get("rich_text", [])
                        value = client.extract_plain_text(text_content)
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
                    elif prop_type == "status":
                        status_data = prop_data.get("status", {})
                        value = status_data.get("name") if status_data else None
                    elif prop_type == "relation":
                        relation_data = prop_data.get("relation", [])
                        value = [item.get("id") for item in relation_data] if relation_data else []
                    elif prop_type in ("created_time", "last_edited_time"):
                        value = prop_data.get(prop_type)
                    elif prop_type in ("created_by", "last_edited_by"):
                        value = extract_person(prop_data.get(prop_type, {}))
                    elif prop_type == "people":
                        people_data = prop_data.get("people", [])
                        value = [extract_person(person) for person in people_data] if people_data else []
                    elif prop_type == "files":
                        files_data = prop_data.get("files", [])
                        value = []
                        for file_item in files_data:
                            file_url = (file_item.get("file") or file_item.get("external") or {}).get("url")
                            value.append({"name": file_item.get("name"), "url": file_url})
                    elif prop_type == "unique_id":
                        unique_id_data = prop_data.get("unique_id", {}) or {}
                        prefix = unique_id_data.get("prefix")
                        number = unique_id_data.get("number")
                        value = f"{prefix}-{number}" if prefix else number
                    elif prop_type == "verification":
                        verification_data = prop_data.get("verification") or {}
                        value = verification_data.get("state")
                    elif prop_type == "formula":
                        formula_data = prop_data.get("formula", {}) or {}
                        formula_result_type = formula_data.get("type")
                        value = formula_data.get(formula_result_type) if formula_result_type else None
                    elif prop_type == "rollup":
                        rollup_data = prop_data.get("rollup", {}) or {}
                        rollup_result_type = rollup_data.get("type")
                        value = rollup_data.get(rollup_result_type) if rollup_result_type else None
                    else:
                        # For other property types, just note the type
                        value = f"<{prop_type}>"
                    
                    formatted_properties[prop_name] = value
                
                # Add to formatted results
                formatted_results.append({
                    "id": page_id,
                    "url": page_url,
                    "properties": formatted_properties
                })
            
            # Return results
            filter_msg = f" with filter {filter_property}={filter_value}" if filter_property and filter_value else ""
            summary = f"Found {len(formatted_results)} results in database{filter_msg}"
            response = {"results": formatted_results}
            if truncated:
                summary += f" (truncated: max_api_calls={max_api_calls} reached, more records remain)"
                response["fetch_truncated"] = True
                response["fetch_truncated_reason"] = (
                    f"max_api_calls={max_api_calls} exceeded; increase the limit to fetch the remaining records."
                )
            yield self.create_text_message(summary)
            yield self.create_json_message(response)
            
        except Exception as e:
            yield self.create_text_message(f"Error querying Notion database: {str(e)}")
            return
