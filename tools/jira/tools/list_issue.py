from collections.abc import Generator
from typing import Any

from atlassian.jira import Jira
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListIssueTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        
        jira_url = self.runtime.credentials.get("jira_url")
        username = self.runtime.credentials.get("username")
        api_token = self.runtime.credentials.get("api_token")
        
        # Changed from board_id to project_key
        project_key = tool_parameters.get("project_key")
        
        # Optional parameters
        status_filter = tool_parameters.get("status")  # Optional status filter
        assignee_filter = tool_parameters.get("assignee")  # Optional assignee filter
        limit = tool_parameters.get("limit", 50)  # Default to 50
        
        jira = Jira(
            url=jira_url,
            username=username,
            password=api_token,
        )
        
        try:
            # Build JQL query based on project key and optional filters
            jql_parts = [f'project="{project_key}"']
            
            if status_filter:
                jql_parts.append(f'status="{status_filter}"')
            
            if assignee_filter:
                if assignee_filter.lower() == "currentuser":
                    jql_parts.append('assignee=currentUser()')
                else:
                    jql_parts.append(f'assignee="{assignee_filter}"')
            
            jql_query = " AND ".join(jql_parts)
            
            # Get issues using JQL search instead of board-based method
            issues_response = jira.jql(
                jql=jql_query,
                start=0,
                limit=limit,
                fields="summary,status,duedate,assignee,priority,issuetype,created,updated,description"
            )
            
            # Extract and format the issues data
            formatted_issues = []
            
            for issue in issues_response.get("issues", []):
                fields = issue.get("fields", {})
                
                # Extract the data you need
                issue_data = {
                    "key": issue.get("key"),
                    "summary": fields.get("summary"),
                    "status": fields.get("status", {}).get("name") if fields.get("status") else None,
                    "due_date": fields.get("duedate"),
                    "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else "Unassigned",
                    "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
                    "issue_type": fields.get("issuetype", {}).get("name") if fields.get("issuetype") else None,
                    "created": fields.get("created"),
                    "updated": fields.get("updated"),
                    "description": fields.get("description", "")[:200] + "..." if fields.get("description") and len(fields.get("description", "")) > 200 else fields.get("description")  # Truncate long descriptions
                }
                
                formatted_issues.append(issue_data)
            
            yield self.create_json_message(
                {
                    "project_key": project_key,
                    "total_issues": issues_response.get("total", 0),
                    "returned_issues": len(formatted_issues),
                    "jql_query": jql_query,
                    "issues": formatted_issues
                }
            )
            
        except Exception as e:
            yield self.create_json_message(
                {
                    "error": f"Error occurred while fetching issues for project {project_key}: {str(e)}",
                    "project_key": project_key
                }
            )
