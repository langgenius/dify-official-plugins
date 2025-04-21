# Linear Plugin for Dify

This plugin integrates Linear's project management capabilities with Dify, allowing you to create, update, search, and manage Linear issues, users, and teams directly from your Dify applications.

## Features

- **Create Issues**: Create new Linear issues with title, description, team, priority, and status.
- **Update Issues**: Modify existing issues by updating their title, description, priority, status, assignee, or labels.
- **Search Issues**: Find issues based on various criteria such as text, team, status, assignee, labels, and priority.
- **Get User Issues**: Retrieve issues assigned to a specific user.
- **Add Comments**: Add comments to existing Linear issues with support for markdown.
- **Get Users**: Search for users by name or email to find their details (including ID/UUID).
- **Get Teams**: Search for teams by name to find their details (including ID).
- **Get My Profile**: Retrieve the profile information of the currently authenticated user.

## Installation

1. Install the plugin through Dify's Plugin Marketplace.
2. Configure the plugin with your Linear Personal API key.

## Authentication

You'll need a **Linear Personal API key** to use this plugin:

1. Log in to your Linear account at [linear.app](https://linear.app)
2. Go to your account settings (click your profile picture in the bottom left)
3. Navigate to **Settings -> Account -> Security & access** (or visit [https://linear.app/settings/account/security](https://linear.app/settings/account/security) directly).
4. Under the **Personal API keys** section, click **Create Key**.
5. Give your key a descriptive label (e.g., \"Dify Integration\").
6. Copy the generated key immediately (it won't be shown again).
7. Paste the key into the **Linear Personal API Key** field in the plugin configuration section in Dify when adding the Linear plugin.

**Important**: Your API key grants access to your Linear account according to its permissions. Keep it secure and never share it publicly.

## Usage

The plugin provides the following tools that can be used in your Dify applications:

### Create Linear Issue

Creates a new issue in Linear with specified title, description, team, priority, and status.

Required parameters:
- `title`: Title of the issue to create
- `teamId`: ID of the team this issue belongs to

Optional parameters:
- `description`: Detailed description of the issue (Markdown supported)
- `priority`: Priority level (0-4, where 0 is no priority and 1 is urgent)
- `status`: Status of the issue (e.g., "Todo", "In Progress", "Done")

### Update Linear Issue

Updates an existing issue in Linear.

Required parameters:
- `id`: ID of the issue to update

Optional parameters:
- `title`: New title for the issue
- `description`: New description for the issue
- `priority`: New priority for the issue (0-4)
- `status`: New workflow State ID for the issue
- `assigneeId`: New assignee ID (use empty string \"\" or \"null\" to unassign)
- `labels`: List of Label IDs to set for the issue (providing an empty list `[]` may clear existing labels, check API behavior)

### Search Linear Issues

Searches for issues in Linear using various criteria.

Optional parameters:
- `query`: Text to search in issue titles and descriptions
- `teamId`: ID of the team to filter issues by
- `status`: Filter issues by status name (e.g., \"In Progress\")
- `assigneeId`: UUID of the user assigned to the issues
- `labels`: Comma-separated list of label names to filter issues by
- `priority`: Filter issues by priority level (1-4)
- `limit`: Maximum number of issues to return (default: 10)
- `includeArchived`: Whether to include archived issues in results

### Get User Issues

Retrieves issues assigned to a specific user.

Required parameter:
- `userId`: UUID of the user whose issues to retrieve.

Optional parameters:
- `teamId`: Filter issues by a specific team ID.
- `state`: Filter issues by a specific state name (e.g., \"Todo\").
- `limit`: Maximum number of issues to return (default: 10, max: 50)

### Add Comment to Issue

Adds a comment to an existing Linear issue.

Required parameters:
- `issueId`: ID of the issue to add a comment to
- `body`: The text content of the comment (Markdown supported)

Optional parameters:
- `createAsUser`: Custom name to display for the comment
- `displayIconUrl`: URL for the avatar icon to display with the comment

### Get Linear Users

Searches for users in Linear by name (partial match) or email (exact match) to retrieve their details.

Optional parameters:
- `name`: Partial name to search for (checks both name and display name, case-insensitive).
- `email`: Exact email address to search for.
- `limit`: Maximum number of users to return (default: 10, max: 50).

*Note: You must provide either `name` or `email`.*

### Get Linear Teams

Searches for teams in Linear by name (partial match, case-insensitive).

Optional parameters:
- `name`: Partial name of the team to search for. If omitted, retrieves all accessible teams (up to limit).
- `limit`: Maximum number of teams to return (default: 10, max: 50).

### Get My Linear Profile

Retrieves the profile information (ID, name, email) of the currently authenticated Linear user (based on the API key used).

No parameters required.

## License

This plugin is licensed under the [MIT License](LICENSE).



