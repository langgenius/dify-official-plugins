# OneDrive Datasource Plugin

Access Microsoft OneDrive files and folders as a datasource for Dify with OAuth 2.0 authentication support.

## Features

- **Secure OAuth Authentication**: Microsoft Azure AD OAuth 2.0 with automatic token refresh
- **File and Folder Access**: Browse and download files from OneDrive for work or school by default
- **Folder Pagination**: Browse large folders with Microsoft Graph pagination
- **Tenant-Aware OAuth**: Supports single-tenant, organization-only multi-tenant, and optional personal-account scenarios

## Upgrade Notes for 1.0.0

- The default Microsoft OAuth tenant changed from `common` to `organizations`.
- Existing connections created before 1.0.0 may not have `tenant_id` or `expires_at` saved.
- Re-authorize existing OneDrive connections after upgrading if refresh fails or the token expires.
- Set `tenant_id` to `common` before authorization only when personal Microsoft accounts are required.

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
- Valid Microsoft work or school account by default
- Personal Microsoft accounts require the app registration and plugin tenant to use `common`
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
   Redirect URI: https://your-dify-domain.com/console/api/oauth/callback
   ```

   Choose the supported account type according to your security policy:

   - Enterprise-only access for your company: choose single tenant and enter that tenant ID or domain in the plugin.
   - Organization-account multi-tenant access: choose organization accounts only and enter `organizations` in the plugin.
   - Personal Microsoft account access: choose the personal-account option only when required and enter `common` in the plugin.

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
   Tenant: organizations or your tenant ID/domain
   ```

### Dify System Configuration

Configure the following in your Dify system settings:

```yaml
# System OAuth Configuration
client_id: "your-azure-app-client-id"
client_secret: "your-azure-app-client-secret"
tenant_id: "organizations"
```

### User Authentication Flow

1. Users click "Connect OneDrive" in Dify datasource configuration
2. Redirected to Microsoft login page
3. Grant permissions to the application
4. Automatically redirected back to Dify with access tokens
5. OneDrive datasource is ready to use

## Microsoft Graph Limits

Microsoft Graph enforces service limits.
If a request is throttled, reduce concurrency or retry later according to the Microsoft Graph response.

- **Requests per app per tenant**: 10,000 requests per 10 minutes
- **Requests per user per app**: 1,000 requests per 10 minutes

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

**Problem**: OAuth token refresh is not working

**Solutions**:
1. Verify refresh_token is present in stored credentials
2. Check that the saved tenant matches the tenant used during authorization
3. Ensure offline_access scope was granted during authorization
4. Re-authorize connections created before 1.0.0 if they do not have tenant or expiry metadata
5. Re-authorize user if refresh_token has been revoked

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
- Keep the offline_access scope enabled so Dify can refresh expired access tokens
- Monitor token usage and expiration
- Revoke compromised tokens immediately

### Access Control
- Grant minimal required permissions
- Regularly review and audit access permissions
- Use conditional access policies where appropriate
- Monitor access logs for suspicious activity

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
**A**: Yes, OneDrive for Business is the default safer path.

Personal OneDrive requires `common` as the plugin tenant and a Microsoft app registration that allows personal Microsoft accounts.

### Q: What happens if my organization has conditional access policies?
**A**: The plugin respects conditional access policies. Users may need to satisfy additional authentication requirements.

### Q: Can I access files offline?
**A**: No, this datasource requires internet connectivity to access Microsoft Graph API.

### Q: Are there file size limits?
**A**: The plugin downloads each file into memory.
Very large files may fail depending on runtime memory limits.

### Q: How often are tokens refreshed?
**A**: Dify refreshes access tokens through the plugin OAuth provider when the saved token reaches its expiry time.

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

## Version: 1.0.0

This plugin implements tenant-aware OneDrive OAuth and Microsoft Graph file access.
