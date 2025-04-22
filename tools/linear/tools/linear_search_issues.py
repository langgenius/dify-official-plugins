import json
from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from client import Linear
from client.Exceptions import LinearQueryException, LinearApiException, LinearAuthenticationException


class LinearSearchIssuesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search for issues in Linear based on provided criteria.

        Args:
            tool_parameters: A dictionary containing the search parameters.

        Yields:
            Messages with the search results or an error message.
        """
        # Extract parameters
        query = tool_parameters.get('query', '')
        team_id = tool_parameters.get('teamId')
        status = tool_parameters.get('status')
        assignee_id = tool_parameters.get('assigneeId')
        labels = tool_parameters.get('labels', '')
        priority = tool_parameters.get('priority')
        limit = int(tool_parameters.get('limit', 10))
        include_archived = tool_parameters.get('includeArchived', False)
        
        # Check credentials
        if "linear_api_key" not in self.runtime.credentials or not self.runtime.credentials.get("linear_api_key"):
            yield self.create_text_message("Linear API Key is required.")
            return
            
        api_key = self.runtime.credentials.get("linear_api_key")
        
        try:
            # Initialize Linear client
            linear_client = Linear(api_key)
            
            # Process labels if provided as a string
            label_list = []
            if labels and isinstance(labels, str):
                label_list = [label.strip() for label in labels.split(',')]
            elif labels and isinstance(labels, list):
                label_list = labels
                
            # Build filter for the search_issues method
            filter_dict = {}
            
            if team_id:
                filter_dict["team"] = {"id": {"eq": team_id}}
            
            if status:
                filter_dict["state"] = {"name": {"eq": status}}
            
            if assignee_id:
                filter_dict["assignee"] = {"id": {"eq": assignee_id}}
            
            if priority is not None:
                try:
                    priority_value = int(priority)
                    if priority_value >= 0 and priority_value <= 4:
                        filter_dict["priority"] = {"eq": priority_value}
                except (ValueError, TypeError):
                    pass
            
            if label_list and len(label_list) > 0:
                if len(label_list) == 1:
                    filter_dict["labels"] = {"name": {"eq": label_list[0]}}
                else:
                    label_conditions = [{"name": {"eq": label}} for label in label_list]
                    filter_dict["labels"] = {"AND": label_conditions}

            # Execute the search using the Linear client
            result = linear_client.search_issues(
                query=query, 
                filter=filter_dict, 
                first=limit
            )
            
            # Extract issues from the response
            issues = result.get("nodes", [])
            
            if not issues:
                yield self.create_text_message("No issues found matching the search criteria.")
                return
            
            # Format issues for better readability
            formatted_issues = []
            for issue in issues:
                # Skip if essential data is missing
                if not issue.get("identifier") or not issue.get("title"):
                    continue
                    
                formatted_issue = {
                    "identifier": issue.get("identifier"),
                    "title": issue.get("title"),
                    "url": issue.get("url", f"https://linear.app/issue/{issue.get('identifier')}"),
                    "priority": issue.get("priority", 0),
                    "state": issue.get("state", {}).get("name") if issue.get("state") else None,
                    "team": issue.get("team", {}).get("name") if issue.get("team") else None,
                    "assignee": issue.get("assignee", {}).get("name") if issue.get("assignee") else None
                }
                
                # Safely handle labels
                labels_data = []
                if issue.get("labels") and issue.get("labels", {}).get("nodes"):
                    for label in issue.get("labels", {}).get("nodes", []):
                        if label.get("name"):
                            labels_data.append(label.get("name"))
                formatted_issue["labels"] = labels_data
                
                formatted_issues.append(formatted_issue)
            
            # Return the formatted issues
            if hasattr(self, 'session') and hasattr(self.session, 'model'):
                # Use model summary if available
                try:
                    summary = self.session.model.summary(content=json.dumps(formatted_issues, ensure_ascii=False))
                    yield self.create_text_message(summary)
                except Exception as e:
                    # Fallback to raw JSON if summary fails
                    yield self.create_text_message(json.dumps(formatted_issues, ensure_ascii=False))
            else:
                # Return raw JSON if model not available
                yield self.create_text_message(json.dumps(formatted_issues, ensure_ascii=False))
                
        except LinearAuthenticationException:
            yield self.create_text_message("Authentication failed. Please check your Linear API key.")
        except LinearApiException as e:
            yield self.create_text_message(f"Linear API error: {str(e)}")
        except LinearQueryException as e:
            yield self.create_text_message(f"Linear query error: {str(e)}")
        except Exception as e:
            yield self.create_text_message(f"Error: Failed to search Linear issues: {str(e)}") 