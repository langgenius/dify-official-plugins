# Dropbox Datasource Plugin

Access your Dropbox files and folders as a datasource for Dify with OAuth 2.0 authentication.

## Features

- **🔐 OAuth 2.0 Authentication**: Secure authentication using Dropbox OAuth 2.0 flow
- **📂 File & Folder Browsing**: Navigate through your Dropbox folder structure
- **⬇️ File Downloads**: Download files directly into Dify workflows
- **🔄 Pagination Support**: Handle large directories with efficient pagination
- **🎯 Smart File ID Handling**: Automatic conversion between file IDs and paths
- **📝 MIME Type Detection**: Automatic file type detection for proper handling
- **🛡️ Error Handling**: Comprehensive error handling with user-friendly messages
- **🚀 High Performance**: Optimized for speed and reliability

## Supported File Types

This plugin supports downloading all file types from Dropbox:

### Documents
- `.pdf` - PDF documents
- `.doc`, `.docx` - Microsoft Word documents
- `.xls`, `.xlsx` - Microsoft Excel spreadsheets
- `.ppt`, `.pptx` - Microsoft PowerPoint presentations
- `.txt` - Plain text files

### Images
- `.jpg`, `.jpeg` - JPEG images
- `.png` - PNG images
- `.gif` - GIF images
- `.bmp` - Bitmap images
- `.svg` - SVG vector graphics

### Media
- `.mp4` - MP4 videos
- `.avi` - AVI videos
- `.mov` - QuickTime videos
- `.mp3` - MP3 audio
- `.wav` - WAV audio

### Archives & Code
- `.zip` - ZIP archives
- `.rar` - RAR archives
- `.tar`, `.gz` - TAR archives
- `.json` - JSON files
- `.xml` - XML files
- `.html`, `.css`, `.js` - Web files
- `.py`, `.java`, `.cpp`, `.c` - Source code files

## Authentication Methods

### OAuth 2.0 (Recommended)
- Secure authentication through Dropbox OAuth flow
- Automatic token management
- Dropbox tokens don't expire (long-lived)
- Granular permission control

## Setup Instructions

### 1. Create Dropbox App

1. Go to [Dropbox App Console](https://www.dropbox.com/developers/apps)
2. Click "Create app"
3. Choose "Scoped access"
4. Choose "Full Dropbox" or "App folder" based on your needs
5. Enter your app name
6. Click "Create app"

### 2. Configure OAuth Settings

1. In your Dropbox app settings, find the "OAuth 2" section
2. Add your Dify redirect URI to "Redirect URIs":
   ```
   https://your-dify-instance.com/console/api/workspaces/current/data-sources/oauth/callback
   ```
3. Note down your **App key** (Client ID) and **App secret** (Client Secret)

### 3. Set Required Permissions

In the "Permissions" tab, enable these scopes:
- `files.metadata.read` - Read file and folder metadata
- `files.content.read` - Download files

### 4. Install in Dify

1. In Dify, go to **Data Sources** → **Add Data Source**
2. Select **Dropbox**
3. Enter your **Client ID** and **Client Secret**
4. Complete the OAuth authorization flow
5. Grant permissions to your Dropbox account

## Usage

### Browse Files
1. After authentication, you can browse your Dropbox files and folders
2. Navigate through directories by clicking on folder names
3. Use the pagination controls for large directories

### Download Files
1. Select files you want to use as data sources
2. Files will be downloaded and made available to your Dify workflows
3. All file metadata (name, size, type) is preserved

### Integration with Dify
- Use downloaded files in Knowledge Base creation
- Process files in Dify workflows
- Extract content for AI analysis
- Support for all common file formats

## Security & Privacy

### Data Protection
- All communication with Dropbox uses HTTPS encryption
- OAuth tokens are securely stored in Dify
- No file content is cached permanently
- Only requested files are downloaded temporarily

### Permissions
- Plugin only accesses files you explicitly authorize
- Follows principle of least privilege
- OAuth tokens can be revoked at any time in Dropbox settings
- Full audit trail of accessed files

### Compliance
- Complies with Dropbox API Terms of Service
- Supports GDPR data protection requirements
- Enterprise-grade security standards
- Regular security updates

## Technical Specifications

### Requirements
- Python 3.12+
- Dify Plugin SDK 0.5.0b14+
- Dropbox Python SDK 12.0.2+

### API Limitations
- Follows Dropbox API rate limits
- Supports files up to Dropbox's maximum file size
- Efficient pagination for large directories
- Automatic retry on transient errors

### Performance
- Optimized for large file downloads
- Smart caching of folder structures
- Minimal memory footprint
- Asynchronous operations where possible

## Troubleshooting

### Common Issues

**Authentication Failed**
- Check your Client ID and Client Secret
- Verify redirect URI is correctly configured
- Ensure Dropbox app has required permissions

**File Not Found**
- Verify file still exists in Dropbox
- Check if file was moved or deleted
- Refresh the file list and try again

**Permission Denied**
- Check if you have access to the file/folder
- Verify OAuth permissions are granted
- Re-authorize if necessary

**Large File Downloads**
- Large files may take longer to download
- Check your network connection
- Consider breaking into smaller chunks

### Support
For technical support:
- Check Dify documentation
- Review Dropbox API documentation
- Contact support through Dify channels

## Version History

### v0.1.0 (Current)
- ✅ Initial release
- ✅ OAuth 2.0 authentication
- ✅ File and folder browsing
- ✅ File downloads with MIME detection
- ✅ Pagination support
- ✅ Comprehensive error handling
- ✅ Smart file ID/path conversion

## License

This plugin is released under the same license as Dify.

---

**Author**: langgenius  
**Version**: 0.1.0  
**Last Updated**: January 2025
