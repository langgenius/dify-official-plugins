# Dropbox Plugin for Dify

**Author:** lcandy  
**Version:** 0.0.1  
**Type:** Tool  

## Description

The Dropbox plugin enables Dify applications to interact with Dropbox files and folders. With this plugin, you can build AI applications that can list, search, upload, download, and manage files in Dropbox.

## Features

- **List Files and Folders**: View the contents of any folder in your Dropbox
- **Search Files**: Find files and folders matching your search criteria
- **Upload Files**: Create new files in your Dropbox
- **Download Files**: Retrieve file content from your Dropbox
- **Create Folders**: Organize your Dropbox by creating new folders
- **Delete Files/Folders**: Remove files or folders from your Dropbox

## Setup

1. Install the plugin in your Dify workspace
2. Create a Dropbox app in the [Dropbox App Console](https://www.dropbox.com/developers/apps)
3. Generate an access token for your Dropbox app
4. Configure the plugin with your access token

## Authentication

This plugin uses OAuth 2.0 for authentication. You'll need to provide an access token with the appropriate permissions for the operations you want to perform.

## Usage Examples

### List files in your Dropbox root folder
```
List all files in my Dropbox
```

### Search for specific files
```
Find all PDF files in my Dropbox
```

### Upload a new file
```
Upload a file named "meeting-notes.txt" to my Dropbox with the content "Meeting scheduled for next Tuesday"
```

### Download file content
```
Download the file "/Documents/important.txt" from my Dropbox
```

## Requirements

- A Dropbox account
- Access token with appropriate permissions
- Dify platform



