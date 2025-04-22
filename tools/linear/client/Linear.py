import json
import requests
import logging

from .Exceptions import LinearApiException, LinearAuthenticationException, LinearRateLimitException

class Linear:
    # Class-level variable to control logging
    _logging_enabled = False
    
    @classmethod
    def enable_logging(cls, enabled=True):
        """
        Enable or disable logging at the class level
        
        Args:
            enabled (bool): True to enable logging, False to disable
        """
        cls._logging_enabled = enabled
    
    @classmethod
    def is_logging_enabled(cls):
        """
        Check if logging is enabled
        
        Returns:
            bool: True if logging is enabled, False otherwise
        """
        return cls._logging_enabled
    
    def __init__(self, LINEAR_API_KEY='', enable_logs=None):
        # Instance-specific logging setting can override the class setting
        self._instance_logging_enabled = enable_logs
        
        self._log("Initializing Linear client...")
        self.set_url('https://api.linear.app/graphql')
        self.set_api_key(LINEAR_API_KEY)
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": self.LINEAR_API_KEY
        }
        self._log(f"Initialization completed. API URL: {self.graphql_url}")

    def set_logging(self, enabled):
        """
        Enable or disable logging for this instance
        
        Args:
            enabled (bool): True to enable logging, False to disable
        """
        self._instance_logging_enabled = enabled
    
    def _should_log(self):
        """
        Determine if logging should be performed based on instance and class settings
        
        Returns:
            bool: True if logging should be performed, False otherwise
        """
        # Instance setting overrides class setting if explicitly set
        if self._instance_logging_enabled is not None:
            return self._instance_logging_enabled
        # Otherwise use class setting
        return Linear._logging_enabled
    
    def _log(self, message):
        """
        Log a message if logging is enabled
        
        Args:
            message (str): The message to log
        """
        if self._should_log():
            print(f"[Linear] {message}")

    def set_url(self, url):
        self._log(f"Setting API URL to: {url}")
        self.graphql_url = url

    def set_api_key(self, LINEAR_API_KEY):
        self._log(f"Setting API key: {'*****' + LINEAR_API_KEY[-4:] if LINEAR_API_KEY and len(LINEAR_API_KEY) > 4 else 'None or too short'}")
        self.LINEAR_API_KEY = LINEAR_API_KEY

    def query_graphql(self, query, variables=None):
        """
        Execute a GraphQL query or mutation against the Linear API
        
        Args:
            query (str): The GraphQL query/mutation string
            variables (dict, optional): Variables for the GraphQL query/mutation
            
        Returns:
            dict: JSON response from the API
            
        Raises:
            LinearAuthenticationException: If authentication fails
            LinearRateLimitException: If rate limit is exceeded
            LinearApiException: For other API errors
        """
        self._log(f"Executing GraphQL query...")
        
        request_data = {"query": query}
        if variables:
            request_data["variables"] = variables
            self._log(f"Query variables: {json.dumps(variables)}")
            
        self._log(f"Request query: {query[:100]}...")
        
        try:
            self._log(f"Sending request to {self.graphql_url}")
            response = requests.post(
                self.graphql_url,
                json=request_data,
                headers=self.headers
            )
            
            self._log(f"Received response with status code: {response.status_code}")
            
            if response.status_code == 401:
                self._log(f"Authentication failed. Status code: {response.status_code}")
                raise LinearAuthenticationException("Authentication failed. Check your API key.")
            
            if response.status_code == 429:
                self._log(f"Rate limit exceeded. Status code: {response.status_code}")
                raise LinearRateLimitException("Rate limit exceeded. Please try again later.")
                
            if response.status_code != 200:
                self._log(f"API request failed. Status code: {response.status_code}, Content: {response.content[:200]}...")
                raise LinearApiException(f"API request failed with status code {response.status_code}")
            
            response_data = json.loads(response.content)
            
            if 'errors' in response_data:
                self._log(f"GraphQL errors in response: {json.dumps(response_data['errors'])}")
                raise LinearApiException(response_data["errors"])
            
            self._log(f"Successfully received data from Linear API")
            return response_data
            
        except requests.exceptions.RequestException as e:
            self._log(f"Network error: {str(e)}")
            raise LinearApiException(f"Network error: {str(e)}")
        except json.JSONDecodeError as e:
            self._log(f"JSON decode error: {str(e)}, Content: {response.content[:200]}...")
            raise LinearApiException(f"Failed to parse response as JSON: {str(e)}")

    def query_basic_resource(self, resource='', first=50, after=None, variables=None):
        """
        Query a basic resource with pagination support
        
        Args:
            resource (str): The resource to query (teams, workflowStates, etc.)
            first (int): Number of items to return (default: 50)
            after (str, optional): Cursor for pagination
            variables (dict, optional): Additional variables for the query
            
        Returns:
            dict: The resource nodes
        """
        self._log(f"Querying basic resource: {resource}, first: {first}, after: {after}")
        
        query_variables = variables or {}
        query_variables.update({
            "first": first,
            "after": after
        })
        
        resource_response = self.query_graphql(
            """
            query Resource($first: Int, $after: String) {
                %s(first: $first, after: $after) {
                    nodes {
                        id
                        name
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
            """ % resource,
            variables=query_variables
        )
        
        if resource in resource_response.get("data", {}):
            nodes_count = len(resource_response["data"][resource].get("nodes", []))
            self._log(f"Retrieved {nodes_count} {resource} records")
        
        return resource_response["data"][resource]

    def create_issue(self, title, description='', project_id='', state_id='', team_id='', assignee_id='', priority=0, labels=None):
        """
        Create a new issue
        
        Args:
            title (str): Issue title
            description (str, optional): Issue description in markdown format
            project_id (str, optional): Project ID
            state_id (str, optional): Workflow state ID
            team_id (str, optional): Team ID
            assignee_id (str, optional): User ID to assign the issue to
            priority (int, optional): Issue priority (0-4)
            labels (list, optional): List of label IDs
            
        Returns:
            dict: Created issue data including ID and success status
        """
        self._log(f"Creating issue: '{title}'")
        
        variables = {
            "title": title,
            "description": description,
            "projectId": project_id,
            "stateId": state_id,
            "teamId": team_id,
            "assigneeId": assignee_id,
            "priority": priority
        }
        
        # Only include labels if provided
        if labels:
            variables["labelIds"] = labels
            self._log(f"Issue will have {len(labels)} labels")
        
        # Filter out empty variables
        variables = {k: v for k, v in variables.items() if v}
        self._log(f"Issue creation parameters: {json.dumps(variables)}")
        
        create_response = self.query_graphql(
            """
            mutation IssueCreate($input: IssueCreateInput!) {
              issueCreate(input: $input) {
                success
                issue {
                  id
                  title
                  description
                  priority
                  url
                }
              }
            }
            """,
            variables={"input": variables}
        )
        
        success = create_response['data']['issueCreate']['success']
        issue_id = create_response['data']['issueCreate']['issue']['id'] if success else None
        self._log(f"Issue creation {'successful' if success else 'failed'}{f', ID: {issue_id}' if issue_id else ''}")
        
        return create_response['data']['issueCreate']

    def update_issue(self, issue_id, title=None, description=None, state_id=None, assignee_id=None, priority=None):
        """
        Update an existing issue
        
        Args:
            issue_id (str): The ID of the issue to update
            title (str, optional): New title
            description (str, optional): New description
            state_id (str, optional): New workflow state ID
            assignee_id (str, optional): New assignee ID
            priority (int, optional): New priority
            
        Returns:
            dict: Updated issue data
        """
        self._log(f"Updating issue: {issue_id}")
        
        variables = {}
        if title:
            variables["title"] = title
        if description:
            variables["description"] = description
        if state_id:
            variables["stateId"] = state_id
        if assignee_id:
            variables["assigneeId"] = assignee_id
        if priority is not None:
            variables["priority"] = priority
        
        self._log(f"Update parameters: {json.dumps(variables)}")
        
        if not variables:
            self._log(f"No update parameters provided for issue {issue_id}")
            return {"success": False, "error": "No update parameters provided"}
        
        update_response = self.query_graphql(
            """
            mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
              issueUpdate(id: $id, input: $input) {
                success
                issue {
                  id
                  title
                  description
                  priority
                  state {
                    id
                    name
                  }
                }
              }
            }
            """,
            variables={"id": issue_id, "input": variables}
        )
        
        success = update_response['data']['issueUpdate']['success']
        self._log(f"Issue update {'successful' if success else 'failed'}")
        
        return update_response['data']['issueUpdate']

    def search_issues(self, query=None, filter=None, first=50, after=None, order_by="updatedAt"):
        """
        Search for issues with filtering support
        
        Args:
            query (str, optional): Text search query
            filter (dict, optional): GraphQL filter object for advanced filtering
            first (int): Number of issues to return
            after (str, optional): Cursor for pagination
            order_by (str): Field to order results by (default: updatedAt)
            
        Returns:
            dict: Issues matching the search criteria
        """
        self._log(f"Searching issues. query: '{query}', orderBy: {order_by}, first: {first}")
        if filter:
            self._log(f"Search filter: {json.dumps(filter)}")
        
        variables = {
            "first": first,
            "after": after,
            "orderBy": order_by
        }
        
        # For text search, include it in the filter if provided
        if query and query.strip():
            if not filter:
                filter = {}
            # Add text search to filter - search in title and description
            filter["or"] = [
                {"title": {"containsIgnoreCase": query}},
                {"description": {"containsIgnoreCase": query}}
            ]
            self._log(f"Added text search to filter: {json.dumps(filter)}")
            
        if filter:
            variables["filter"] = filter
            
        search_response = self.query_graphql(
            """
            query SearchIssues($first: Int, $after: String, $orderBy: PaginationOrderBy, $filter: IssueFilter) {
              issues(first: $first, after: $after, orderBy: $orderBy, filter: $filter) {
                nodes {
                  id
                  title
                  identifier
                  description
                  priority
                  createdAt
                  updatedAt
                  state {
                    id
                    name
                    type
                  }
                  assignee {
                    id
                    name
                  }
                  labels {
                    nodes {
                      id
                      name
                      color
                    }
                  }
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
            """,
            variables=variables
        )
        
        issues_count = len(search_response['data']['issues']['nodes'])
        has_next = search_response['data']['issues']['pageInfo']['hasNextPage']
        self._log(f"Search found {issues_count} issues{', with more results available' if has_next else ''}")
        
        return search_response['data']['issues']

    def get_issue(self, issue_id):
        """
        Get a specific issue by ID
        
        Args:
            issue_id (str): The ID of the issue
            
        Returns:
            dict: Issue data
        """
        self._log(f"Getting issue: {issue_id}")
        
        issue_response = self.query_graphql(
            """
            query Issue($id: String!) {
              issue(id: $id) {
                id
                title
                identifier
                description
                priority
                createdAt
                updatedAt
                state {
                  id
                  name
                  type
                }
                assignee {
                  id
                  name
                }
                labels {
                  nodes {
                    id
                    name
                    color
                  }
                }
              }
            }
            """,
            variables={"id": issue_id}
        )
        
        issue = issue_response['data']['issue']
        if issue:
            self._log(f"Retrieved issue: {issue.get('identifier', '')} - {issue.get('title', '')}")
        else:
            self._log(f"Issue not found: {issue_id}")
        
        return issue_response['data']['issue']

    def get_viewer(self):
        """
        Get information about the authenticated user
        
        Returns:
            dict: User data for the authenticated user
        """
        self._log(f"Getting viewer (authenticated user) information")
        
        viewer_response = self.query_graphql(
            """
            query Me {
              viewer {
                id
                name
                email
              }
            }
            """
        )
        
        viewer = viewer_response['data']['viewer']
        self._log(f"Retrieved viewer info: {viewer.get('name')} ({viewer.get('email')})")
        
        return viewer_response['data']['viewer']

    def teams(self, first=50, after=None):
        """Get all teams with pagination support"""
        self._log(f"Getting teams list")
        return self.query_basic_resource('teams', first, after)

    def states(self, first=50, after=None):
        """Get all workflow states with pagination support"""
        self._log(f"Getting workflow states list")
        return self.query_basic_resource('workflowStates', first, after)

    def projects(self, first=50, after=None):
        """Get all projects with pagination support"""
        self._log(f"Getting projects list")
        return self.query_basic_resource('projects', first, after)

    def labels(self, first=50, after=None):
        """Get all labels with pagination support"""
        self._log(f"Getting labels list")
        return self.query_basic_resource('issueLabels', first, after)

    def users(self, first=50, after=None):
        """Get all users with pagination support"""
        self._log(f"Getting users list")
        return self.query_basic_resource('users', first, after)

    def get_team_issues(self, team_id, first=50, after=None, filter=None):
        """
        Get issues for a specific team
        
        Args:
            team_id (str): Team ID
            first (int): Number of issues to return
            after (str, optional): Cursor for pagination
            filter (dict, optional): Filter criteria
            
        Returns:
            dict: Team issues data
        """
        self._log(f"Getting issues for team: {team_id}")
        if filter:
            self._log(f"Team issues filter: {json.dumps(filter)}")
        
        variables = {
            "id": team_id,
            "first": first,
            "after": after
        }
        
        if filter:
            variables["filter"] = filter
            
        team_response = self.query_graphql(
            """
            query Team($id: String!, $first: Int, $after: String, $filter: IssueFilter) {
              team(id: $id) {
                id
                name
                issues(first: $first, after: $after, filter: $filter) {
                  nodes {
                    id
                    title
                    identifier
                    description
                    priority
                    createdAt
                    updatedAt
                    state {
                      id
                      name
                    }
                    assignee {
                      id
                      name
                    }
                  }
                  pageInfo {
                    hasNextPage
                    endCursor
                  }
                }
              }
            }
            """,
            variables=variables
        )
        
        team = team_response['data']['team']
        if team:
            issues_count = len(team.get('issues', {}).get('nodes', []))
            self._log(f"Retrieved {issues_count} issues for team: {team.get('name', team_id)}")
        
        return team_response['data']['team']
        
    # Backward compatibility with old name
    def query_grapql(self, query):
        """Legacy method for backward compatibility"""
        self._log(f"Using legacy query_grapql method")
        return self.query_graphql(query)

