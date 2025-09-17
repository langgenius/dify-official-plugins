# Google Drive Datasource Plugin

**Author**: langgenius  
**Version**: 0.1.5
**Type**: datasource

## Introduction

This plugin integrates with Google Drive, enabling automated access to your files and folders stored in Google Drive. It supports browsing files, navigating folders, and downloading files directly for use in platforms like Dify. The plugin also handles Google Workspace files (Docs, Sheets, Slides) by exporting them to compatible formats.

## Features

- **Browse Files and Folders**: Navigate through your Google Drive directory structure
- **Download Files**: Retrieve files from Google Drive for processing
- **Google Workspace Support**: Automatic export of Google Docs, Sheets, and Slides to compatible formats
- **Folder Navigation**: Support for hierarchical folder structure browsing
- **Pagination Support**: Efficiently handle large numbers of files with pagination
- **OAuth 2.0 Authentication**: Secure authentication using Google's OAuth 2.0 flow

## Setup

### Prerequisites

Before using this plugin, you need:
1. A Google account with Google Drive enabled
2. Access to Google Cloud Console to create OAuth 2.0 credentials
3. Files in your Google Drive that you want to access

### Configuration Steps

1. **Create a Google Cloud Project**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Click "Create Project" or select an existing project
   - Give your project a name (e.g., "Dify Google Drive Plugin")

2. **Enable Google Drive API**:
   - In your Google Cloud project, go to "APIs & Services" → "Library"
   - Search for "Google Drive API"
   - Click on it and press "Enable"

3. **Create OAuth 2.0 Credentials**:
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - If prompted, configure the OAuth consent screen first:
     - **User Type**: Choose based on your needs (Internal for organization use, External for general use)
     - **App name**: Dify Google Drive Plugin
     - **User support email**: Your email address
     - **Developer contact information**: Your email address
   - For the OAuth client ID:
     - **Application type**: Web application
     - **Name**: Dify Google Drive Plugin
     - **Authorized redirect URIs**: 
       - For SaaS (cloud.dify.ai) users: `https://cloud.dify.ai/console/api/oauth/plugin/langgenius/google_drive/google_drive/datasource/callback`
       - For self-hosted users: `http://<YOUR CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/google_drive/google_drive/datasource/callback`
       - Replace `<YOUR CONSOLE_API_URL>` with your actual console API URL

4. **Configure OAuth Consent Screen**:
   - Add the following OAuth scopes:
     - `https://www.googleapis.com/auth/drive.readonly` - View and download all files
     - `https://www.googleapis.com/auth/drive.metadata.readonly` - View metadata for files
   - Add test users if your app is in testing mode

5. **Get Your Credentials**:
   - After creating the OAuth client, copy:
     - **Client ID**
     - **Client Secret**
   - Keep these secure as they will be needed in Dify

6. **Configure the Plugin in Dify**:
   - Navigate to the datasource plugins section in Dify
   - Select Google Drive
   - Enter your **Client ID** and **Client Secret**
   - Click "Save and authorize"
   - You'll be redirected to Google's OAuth consent page
   - Grant the necessary permissions
   - You'll be redirected back to Dify upon successful authorization

## Usage

### Browsing Files

The plugin provides an interface for browsing Google Drive content:

1. **Root Directory**: Start by browsing from the root of your Google Drive
2. **Folder Navigation**: Click on folders to browse their contents
3. **File Information**: View file names, sizes, and types
4. **Pagination**: Navigate through pages when you have many files

### Downloading Files

To download a file:
1. Browse to locate the desired file
2. Select the file for download
3. The plugin retrieves the file content and metadata

### Google Workspace Files

The plugin automatically handles Google Workspace files:
- **Google Docs**: Exported as PDF
- **Google Sheets**: Exported as Excel (XLSX)
- **Google Slides**: Exported as PDF
- **Google Drawings**: Exported as PNG
- **Google Forms**: Exported as PDF

## Supported Operations

| Operation | Description |
|-----------|-------------|
| List Files | Browse files and folders in Google Drive |
| Navigate Folders | Access files within specific folders |
| Download File | Retrieve file content from Google Drive |
| Export Workspace Files | Automatic conversion of Google Workspace files |
| Pagination | Handle large file lists with page tokens |

## Troubleshooting

### Common Issues

1. **"Authentication failed (401 Unauthorized)" error**:
   - The access token has expired
   - Solution: Reauthorize the connection in Dify settings

2. **"File not found" error**:
   - The file may have been deleted or moved
   - You may not have permission to access the file
   - Solution: Verify the file exists and you have access

3. **"Failed to list files" error**:
   - Check your internet connection
   - Verify API quotas haven't been exceeded
   - Ensure Google Drive API is enabled in your project

4. **OAuth Authorization Issues**:
   - Verify redirect URI matches exactly (including protocol and trailing slashes)
   - Check that all required scopes are configured
   - Ensure client ID and secret are correct

5. **Files Not Showing**:
   - Check if files are in trash (trashed files are not shown)
   - Verify you have permission to view the files
   - Ensure the parent folder ID is correct when browsing subfolders

## API Quotas and Limits

Google Drive API has usage quotas:
- **Queries per day**: 1,000,000,000
- **Queries per 100 seconds per user**: 1,000
- **Queries per 100 seconds**: 10,000

If you encounter quota errors, wait before retrying or request a quota increase in Google Cloud Console.

## Security Considerations

- **OAuth 2.0**: Uses secure OAuth 2.0 flow for authentication
- **Token Storage**: Access and refresh tokens are stored securely
- **Minimal Permissions**: Only requests read-only access to files
- **HTTPS**: All API communications use encrypted HTTPS connections
- **Token Refresh**: Automatically refreshes expired tokens when possible

## Privacy

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

## Support

For issues or questions:
- Contact: [hello@dify.ai](mailto:hello@dify.ai)
- Repository: Check the project repository for updates and documentation
- Google Drive API Documentation: [https://developers.google.com/drive/api/v3/about-sdk](https://developers.google.com/drive/api/v3/about-sdk)

## Additional Resources

- [Google Drive API Reference](https://developers.google.com/drive/api/v3/reference)
- [OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google Cloud Console](https://console.cloud.google.com/)

Last updated: September 2025
