import json
import requests
from typing import Optional, Dict, Any, Union, List

from dify_plugin.entities.tool import ToolInvokeMessage


class LinearQueryException(Exception):
    """Exception raised when Linear GraphQL query fails."""
    pass


class LinearClient:
    """Client for interacting with the Linear API."""
    
    def __init__(self, api_key: str = ''):
        """Initialize the Linear client.
        
        Args:
            api_key: The Linear API key for authentication.
        """
        self.graphql_url = 'https://api.linear.app/graphql'
        self.api_key = api_key
        self.headers = {
            "Authorization": f"{api_key}",
            "Content-Type": "application/json"
        }
    
    def execute_graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a GraphQL query against the Linear API.

        Args:
            query: The GraphQL query string.
            variables: Optional variables for the query.

        Returns:
            The JSON response from the API.
            
        Raises:
            LinearQueryException: If the query fails.
        """
        payload = {'query': query}
        if variables:
            payload['variables'] = variables

        response = requests.post(
            self.graphql_url,
            headers=self.headers,
            json=payload
        )

        if response.status_code != 200:
            raise LinearQueryException(f"Query failed with status code {response.status_code}: {response.text}")

        result = response.json()
        
        if 'errors' in result:
            raise LinearQueryException(result['errors'])

        return result
    
    def query_basic_resource(self, resource: str) -> List[Dict[str, Any]]:
        """Query a basic resource from Linear.
        
        Args:
            resource: The name of the resource to query.
            
        Returns:
            A list of resources with id and name.
        """
        resource_response = self.execute_graphql(
            f"""
            query Resource {{{resource}{{nodes{{id,name}}}}}}
            """
        )
        return resource_response["data"][resource]["nodes"]
    
    def teams(self) -> List[Dict[str, Any]]:
        """Get all teams.
        
        Returns:
            A list of teams.
        """
        return self.query_basic_resource('teams')
    
    def states(self) -> List[Dict[str, Any]]:
        """Get all workflow states.
        
        Returns:
            A list of workflow states.
        """
        return self.query_basic_resource('workflowStates')
    
    def projects(self) -> List[Dict[str, Any]]:
        """Get all projects.
        
        Returns:
            A list of projects.
        """
        return self.query_basic_resource('projects')
    
    def create_text_message(self, text: str) -> ToolInvokeMessage:
        """Create a text message response.
        
        Args:
            text: The text content.
            
        Returns:
            A ToolInvokeMessage with text content.
        """
        return ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.TEXT,
            message=ToolInvokeMessage.TextMessage(text=text)
        )
    
    def create_json_message(self, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> ToolInvokeMessage:
        """Create a JSON message response.
        
        Args:
            data: The data to convert to JSON.
            
        Returns:
            A ToolInvokeMessage with JSON content.
        """
        return ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.JSON,
            message=ToolInvokeMessage.JsonMessage(json_object=data)
        )


def create_tool_response(data: Union[str, Dict[str, Any], List[Dict[str, Any]]]) -> ToolInvokeMessage:
    """Create a tool response message.
    
    Args:
        data: The data to include in the response. Can be a string, dictionary, or list.
        
    Returns:
        A ToolInvokeMessage with the data properly formatted.
    """
    # Create a temporary client just to use the message creation methods
    client = LinearClient()
    
    if isinstance(data, str):
        return client.create_text_message(data)
    else:
        return client.create_json_message(data) 