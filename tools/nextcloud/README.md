# NextCloud Plugin for Dify

This plugin integrates NextCloud's file management capabilities with Dify, allowing you to browse, download, upload, create, delete, and search files and folders in your NextCloud instance directly from your Dify applications.

## Features

- **List Files**: Browse and list files and directories in any NextCloud folder with detailed metadata.
- **Download File**: Download files from NextCloud with optional content reading for text and binary files.
- **Upload File**: Upload text content or base64-encoded binary data to NextCloud with automatic directory creation.
- **Create Folder**: Create new directories in NextCloud with path validation.
- **Delete File/Folder**: Permanently remove files and folders from NextCloud with confirmation.
- **Search Files**: Find files and folders using name patterns with wildcard support and recursive search.

## Installation

1. Install the plugin through Dify's Plugin Marketplace.
2. Configure the plugin with your NextCloud server URL, username, and app password.

## Authentication

You'll need a **NextCloud App Password** to use this plugin securely:

1. Log in to your NextCloud instance
2. Go to your account settings (click your profile picture in the top right)
3. Navigate to **Settings** → **Security** → **App passwords** (or visit your NextCloud URL + `/settings/user/security` directly)
4. Under the **App passwords** section, enter a name for your app (e.g., "Dify Integration")
5. Click **Create new app password**
6. Copy the generated password immediately (it won't be shown again)
7. When configuring the plugin in Dify, provide:
   - **NextCloud Server URL**: Your NextCloud instance URL (e.g., `https://cloud.example.com`)
   - **Username**: Your NextCloud username
   - **App Password**: The app password you just generated

**Important**: Your app password grants access to your NextCloud account according to your user permissions. Keep it secure and never share it publicly. Using app passwords is more secure than using your main account password.

## Usage

The plugin provides the following tools that can be used in your Dify applications:

### List Files

Lists files and directories in a specified NextCloud folder with detailed information.

Optional parameters:
- `path`: The folder path to list (default: "/")
- `include_size`: Whether to include file size information (default: "true")

### Download File

Downloads a file from NextCloud and optionally reads its content.

Required parameters:
- `file_path`: Full path to the file to download

Optional parameters:
- `include_content`: Whether to include file content in response (default: "false")

*Note: For text files, content is returned as readable text. For binary files, content is returned as base64-encoded string.*

### Upload File

Uploads a file to NextCloud from text content or base64-encoded binary data.

Required parameters:
- `file_path`: Destination path for the uploaded file
- `content`: File content (text or base64 encoded)

Optional parameters:
- `content_type`: Content type - "text" for plain text or "base64" for binary data (default: "text")

### Create Folder

Creates a new folder/directory in NextCloud.

Required parameters:
- `folder_path`: Full path for the new folder including the folder name

*Note: Parent directories must already exist.*

### Delete File/Folder

Permanently deletes a file or folder from NextCloud.

Required parameters:
- `file_path`: Full path to the file or folder to delete

**Warning**: This operation permanently deletes the item and cannot be undone.

### Search Files

Searches for files and folders in NextCloud that match a specified name pattern.

Required parameters:
- `search_pattern`: Name pattern to search for (supports wildcards like "*.txt", "*report*")

Optional parameters:
- `search_path`: Starting directory for search (default: "/")
- `max_results`: Maximum number of results to return (default: "50")

*Note: Searches recursively through directories and supports wildcard patterns for flexible file discovery.*

## Examples

Here are some example usage scenarios:

```
# List all files in Documents folder
"List all files in my Documents folder"

# Download a specific file with content
"Download the contents of /Documents/meeting_notes.txt"

# Create a new project folder
"Create a new folder called /Projects/WebApp"

# Upload text content as a file
"Upload this summary as a file to /Documents/project_summary.txt: [your content here]"

# Search for all PDF files
"Search for all PDF files in my Documents folder"

# Delete an old backup file
"Delete the old backup file at /Backups/old_backup.zip"
```

## Security Considerations

- **App Passwords**: Always use NextCloud app passwords instead of your main account password for enhanced security
- **HTTPS**: Ensure your NextCloud server uses HTTPS for secure communication
- **Permissions**: The plugin will have the same access rights as your NextCloud user account
- **Path Validation**: All file paths are validated and must start with "/" for security

## Troubleshooting

### Authentication Issues
- Verify your NextCloud server URL is correct and accessible
- Ensure the app password is correctly entered (no extra spaces)
- Check that your NextCloud account has the necessary permissions
- Confirm that WebDAV is enabled on your NextCloud server

### Connection Problems
- Verify your NextCloud server has WebDAV enabled
- Check that the server URL includes the protocol (https://)
- Test connectivity to your NextCloud instance from your network
- Verify firewall settings if accessing a private NextCloud instance

### Path and File Errors
- Paths are case-sensitive - ensure exact spelling
- Always start paths with "/" for absolute paths
- Use forward slashes (/) for all path separators
- Ensure parent directories exist before creating files or subdirectories

## Technical Details

- **Protocol**: WebDAV over HTTPS
- **Authentication**: HTTP Basic Authentication with NextCloud app passwords
- **WebDAV Endpoint**: `/remote.php/webdav/` (automatically appended to server URL)
- **Dependencies**: `webdavclient3~=3.14.6`
- **File Support**: Text files, binary files (via base64 encoding), and all standard file operations

## License

This plugin is licensed under the same license terms as the Dify platform.



