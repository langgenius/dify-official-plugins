# OneDrive Datasource Plugin

Access Microsoft OneDrive files and folders as a datasource for Dify with comprehensive OAuth 2.0 authentication support.

## Features

- **Secure OAuth Authentication**: Microsoft Azure AD OAuth 2.0 with automatic token refresh
- **File and Folder Access**: Browse and download files from personal and business OneDrive
- **Real-time Synchronization**: Access up-to-date file content and metadata
- **Rate Limit Handling**: Automatic Microsoft Graph API rate limit management
- **Large File Support**: Efficient handling of large file downloads
- **Multi-Tenant Support**: Works with personal and business Microsoft accounts

## Supported Content Types

- All file types stored in OneDrive
- Microsoft Office documents (Word, Excel, PowerPoint)
- PDF and text documents
- Images and multimedia files
- Code and configuration files
- Compressed archives and other binary formats

## Setup and Installation

### Requirements

- Dify platform version >= 1.9.0
- Python 3.12+
- Valid Microsoft account (personal or business)
- Azure AD App Registration (for OAuth)

### Installation Steps

1. **Install the Plugin**
   - Add the OneDrive datasource plugin to your Dify instance
   - Ensure all dependencies are installed

2. **Create Azure AD App Registration**
   - Go to Azure Portal > Azure Active Directory > App registrations
   - Click "New registration"
   - Configure your app (see detailed steps below)

3. **Configure Plugin**
   - Add OAuth credentials in Dify system settings
   - Test the connection with a user account

## Authentication Setup

### Azure AD App Registration

1. **Create New App Registration**
   ```
   Name: Dify OneDrive Integration
   Supported account types: Accounts in any organizational directory and personal Microsoft accounts
   Redirect URI: https://your-dify-domain.com/console/api/oauth/callback
   ```

2. **Configure API Permissions**
   ```
   Microsoft Graph:
   - offline_access (Delegated)
   - User.Read (Delegated)  
   - Files.Read (Delegated)
   - Files.Read.All (Delegated)
   ```

3. **Generate Client Secret**
   ```
   Go to: Certificates & secrets > New client secret
   Description: Dify OneDrive Integration
   Expires: 24 months (recommended)
   ```

4. **Note Configuration Values**
   ```
   Application (client) ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   Client Secret: your-generated-secret
   ```

### Dify System Configuration

Configure the following in your Dify system settings:

```yaml
# System OAuth Configuration
client_id: "your-azure-app-client-id"
client_secret: "your-azure-app-client-secret"
```

### User Authentication Flow

1. Users click "Connect OneDrive" in Dify datasource configuration
2. Redirected to Microsoft login page
3. Grant permissions to the application
4. Automatically redirected back to Dify with access tokens
5. OneDrive datasource is ready to use

## Usage Examples

### Basic Datasource Configuration

```yaml
# datasources/onedrive_datasource.yaml
name: onedrive_datasource
type: online_drive
provider: onedrive_datasource
config:
  max_files_per_request: 50
  auto_refresh_tokens: true
```

### Browsing Files

```python
# Example: Browse root folder
request = OnlineDriveBrowseFilesRequest(
    bucket="onedrive",
    prefix="root",
    max_keys=20
)

response = datasource.browse_files(request)
for bucket in response.result:
    for file in bucket.files:
        print(f"File: {file.name}, Size: {file.size}, Type: {file.type}")
```

### Downloading Files

```python
# Example: Download a specific file
request = OnlineDriveDownloadFileRequest(
    id="file-id-from-browse-response"
)

for message in datasource.download_file(request):
    # Process downloaded content
    if message.type == "blob":
        file_content = message.content
        metadata = message.meta
```

## Environment Variables

### Required System Variables
```bash
# Azure AD OAuth Configuration
ONEDRIVE_CLIENT_ID="your-azure-app-client-id"
ONEDRIVE_CLIENT_SECRET="your-azure-app-client-secret"

# Optional: Custom Microsoft Graph Endpoints
GRAPH_API_BASE_URL="https://graph.microsoft.com/v1.0"
OAUTH_TOKEN_URL="https://login.microsoftonline.com/common/oauth2/v2.0/token"
```

### Development Environment
```bash
# For local development
export ONEDRIVE_CLIENT_ID="your-development-client-id"
export ONEDRIVE_CLIENT_SECRET="your-development-client-secret"
export DIFY_DEBUG=true
```

## Rate Limits and Performance

### Microsoft Graph API Limits

- **Requests per app per tenant**: 10,000 requests per 10 minutes
- **Requests per user per app**: 1,000 requests per 10 minutes
- **Download limits**: 4 GB per file download

### Plugin Optimizations

- Automatic retry with exponential backoff on rate limit hits
- Intelligent request batching for multiple file operations
- Efficient pagination handling for large folder listings
- Smart caching of metadata to reduce API calls

## Troubleshooting

### Common Issues

#### "Invalid OAuth Token" Error

**Problem**: Authentication fails after initial setup

**Solutions**:
1. Check if access token has expired (tokens expire after 1 hour)
2. Verify refresh token is available and valid
3. Ensure Azure AD app permissions are properly configured
4. Re-authorize user through OAuth flow if refresh fails

**Debug Steps**:
```bash
# Check token expiration
curl -H "Authorization: Bearer YOUR_TOKEN" \
     "https://graph.microsoft.com/v1.0/me"

# If 401 Unauthorized, token needs refresh or re-authorization
```

#### "Rate Limit Exceeded" Error

**Problem**: Too many requests to Microsoft Graph API

**Solutions**:
1. Wait for rate limit reset (indicated in error response)
2. Reduce the number of files being processed simultaneously
3. Implement custom retry logic in your application
4. Consider pagination for large folder operations

#### "Permission Denied" Error

**Problem**: Cannot access specific files or folders

**Solutions**:
1. Verify Azure AD app has required Graph API permissions
2. Check user has access to the specific OneDrive content
3. Ensure proper admin consent for organizational accounts
4. Verify Files.Read.All scope for shared content access

#### Token Refresh Failures

**Problem**: Automatic token refresh not working

**Solutions**:
1. Verify refresh_token is present in stored credentials
2. Check Azure AD app configuration allows refresh tokens
3. Ensure offline_access scope was granted during authorization
4. Re-authorize user if refresh_token has been revoked

### Debug Mode

Enable detailed logging for troubleshooting:

```python
import logging
logging.getLogger('datasources.onedrive').setLevel(logging.DEBUG)
```

### Health Check Endpoint

Test datasource connectivity:
```bash
# Basic connectivity test
curl -X POST "https://your-dify-domain.com/api/datasources/onedrive/test" \
     -H "Authorization: Bearer YOUR_DIFY_TOKEN" \
     -H "Content-Type: application/json"
```

## Security Best Practices

### OAuth Configuration
- Use secure redirect URIs (HTTPS only)
- Implement proper scope validation
- Regularly rotate client secrets
- Monitor OAuth application usage

### Token Management
- Store tokens securely using Dify's encrypted storage
- Implement proper token refresh logic
- Monitor token usage and expiration
- Revoke compromised tokens immediately

### Access Control
- Grant minimal required permissions
- Regularly review and audit access permissions
- Use conditional access policies where appropriate
- Monitor access logs for suspicious activity

## Integration Examples

### Knowledge Base Integration

```yaml
# Example: Document knowledge base from OneDrive
datasource_config:
  name: "Company Documentation"
  type: onedrive_datasource
  filters:
    file_types: [".md", ".docx", ".pdf"]
    folder_paths: ["/Documentation", "/Policies"]
  processing:
    chunking_strategy: "semantic"
    embedding_model: "text-embedding-ada-002"
```

### Automated Content Processing

```python
# Example: Process all markdown files
async def process_documentation():
    files = await onedrive_datasource.browse_files({
        "prefix": "Documentation",
        "file_filter": "*.md"
    })
    
    for file in files:
        content = await onedrive_datasource.download_file(file.id)
        # Process with Dify's document processor
        processed = await dify.process_document(content)
        await knowledge_base.add_document(processed)
```

## Limitations and Considerations

### Current Limitations
- Single tenant support per datasource instance
- No real-time change notifications (polling-based)
- Limited to files accessible through Microsoft Graph API
- No support for SharePoint lists or other Microsoft 365 content

### Performance Considerations
- Large folders may require pagination and multiple requests
- File downloads are subject to Microsoft Graph API timeouts
- Concurrent access may be throttled by Microsoft's rate limits
- Network latency affects file browsing and download performance

### Business Account Considerations
- May require admin consent for organizational accounts
- Conditional access policies may affect access
- Multi-factor authentication may be required
- Data residency requirements must be considered

## FAQ

### Q: Can I access shared files from other users?
**A**: Yes, with Files.Read.All permission, you can access files shared with your account.

### Q: Does this work with OneDrive for Business?
**A**: Yes, supports both personal OneDrive and OneDrive for Business accounts.

### Q: What happens if my organization has conditional access policies?
**A**: The plugin respects conditional access policies. Users may need to satisfy additional authentication requirements.

### Q: Can I access files offline?
**A**: No, this datasource requires internet connectivity to access Microsoft Graph API.

### Q: Are there file size limits?
**A**: Microsoft Graph API supports files up to 4 GB. Larger files may require special handling.

### Q: How often are tokens refreshed?
**A**: Access tokens are automatically refreshed when they expire (typically every hour).

## Support and Resources

### Documentation
- [Dify Documentation](https://docs.dify.ai)
- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/)
- [Azure AD OAuth 2.0 Documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-auth-code-flow)

### Community
- Dify Community Forums
- GitHub Issues and Discussions
- Microsoft Graph Developer Community

### Professional Support
- Dify Enterprise Support
- Microsoft Premier Support (for Graph API issues)
- Custom integration consulting available

## Version: 0.1.3

This plugin implements comprehensive OneDrive integration with enterprise-grade security, OAuth 2.0 authentication, and seamless file access capabilities.
