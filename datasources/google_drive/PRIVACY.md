# Privacy Policy

This Privacy Policy explains how we collect, use, and protect your information when you use the Google Drive Datasource Plugin for Dify.

## Information Collection

We do not collect, store, or share any personal information from users. All data processed by the plugin is handled locally or through secure connections to Google Drive services, as required for functionality.

## Use of Information

The plugin only accesses your Google Drive files and folders to provide the requested features, such as browsing and downloading files from your Google Drive. No data is stored or transmitted to third parties by the plugin itself.

## Data Security

We are committed to ensuring the security of your data. All communications with Google Drive services use secure protocols (HTTPS) and OAuth 2.0 authentication. We do not retain any user credentials or file data beyond the duration of your session.

## Third-Party Services

This plugin interacts with Google Drive via official Google APIs. Please refer to Google's privacy policy for details on how your data is handled by Google services:
- [Google Privacy Policy](https://policies.google.com/privacy)
- [Google Drive Terms of Service](https://workspace.google.com/terms/user_features.html)

## Data Access Scope

The plugin requires the following OAuth 2.0 scopes to function:
- `https://www.googleapis.com/auth/drive.readonly`: Read-only access to view and download files from Google Drive
- `https://www.googleapis.com/auth/drive.file`: Access to files created or opened by the app (if applicable)
- `https://www.googleapis.com/auth/drive.metadata.readonly`: Read-only access to file metadata

These permissions are used solely for the intended functionality and no additional data is accessed.

## OAuth 2.0 Authentication

This plugin uses OAuth 2.0 for authentication with Google services:
- Your Google credentials are never directly accessed by the plugin
- Authentication tokens are stored securely and only for the duration of your session
- Refresh tokens are used to maintain access without requiring repeated authentication
- You can revoke access at any time through your Google Account settings

## Data Processing

When using this plugin:
- File metadata (names, sizes, types) is retrieved to display file listings
- File content is downloaded only when explicitly requested by the user
- Google Workspace files (Docs, Sheets, Slides) are exported to compatible formats (PDF, Excel, etc.)
- No files are modified or deleted through this plugin

## User Rights

You have the right to:
- Revoke the plugin's access to your Google Drive at any time
- Request information about what data is accessed
- Control which files and folders the plugin can access

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: December 2024
