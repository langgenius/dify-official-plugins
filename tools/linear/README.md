# Linear Plugin for Dify

This plugin integrates Linear's project management capabilities with Dify, allowing you to create, update, search, and manage Linear issues directly from your Dify applications.

## Features

- **Create Issues**: Create new Linear issues with title, description, team, priority, and status.
- **Update Issues**: Modify existing issues by updating their title, description, priority, or status.
- **Search Issues**: Find issues based on various criteria such as text, team, status, assignee, and priority.
- **Get User Issues**: Retrieve issues assigned to a specific user or the currently authenticated user.
- **Add Comments**: Add comments to existing Linear issues with support for markdown.

## Installation

1. Install the plugin through Dify's Plugin Marketplace.
2. Configure the plugin with your Linear API key.

## Authentication

You'll need a Linear API key to use this plugin:

1. Log in to your Linear account at [linear.app](https://linear.app)
2. Go to your account settings (click your profile picture in the bottom left)
3. Click on "API" in the sidebar
4. Click "Create Key" button to generate a new personal API key
5. Give your key a name (e.g., "Dify Integration")
6. Copy the generated key immediately (it won't be shown again)
7. Paste the key into the plugin configuration in Dify

**Important**: Your API key has full access to your Linear account. Keep it secure and never share it publicly.

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
- `priority`: New priority for the issue
- `status`: New status for the issue

### Search Linear Issues

Searches for issues in Linear using various criteria.

Optional parameters:
- `query`: Text to search in issue titles and descriptions
- `teamId`: ID of the team to filter issues by
- `status`: Filter issues by status name
- `assigneeId`: ID of the user assigned to the issues
- `labels`: Array of label names to filter issues by
- `priority`: Filter issues by priority level
- `limit`: Maximum number of issues to return (default: 10)
- `includeArchived`: Whether to include archived issues in results

### Get User Issues

Retrieves issues assigned to a specific user or the currently authenticated user.

Optional parameters:
- `userId`: ID of the user whose issues to retrieve (leave empty for authenticated user)
- `includeArchived`: Whether to include archived issues in results
- `limit`: Maximum number of issues to return (default: 50)

### Add Comment to Issue

Adds a comment to an existing Linear issue.

Required parameters:
- `issueId`: ID of the issue to add a comment to
- `body`: The text content of the comment (Markdown supported)

Optional parameters:
- `createAsUser`: Custom name to display for the comment
- `displayIconUrl`: URL for the avatar icon to display with the comment

## License

This plugin is licensed under the [MIT License](LICENSE).



