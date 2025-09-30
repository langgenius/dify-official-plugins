# GitHub Datasource Plugin

Access GitHub repositories, issues, pull requests, and wiki pages as a datasource for Dify with comprehensive authentication support.

## Features

- **Repository Access**: Browse and download files from public and private repositories
- **Issues & Pull Requests**: Access issue and PR content with comments
- **Multiple Authentication**: Support both Personal Access Token and OAuth
- **Rate Limit Handling**: Automatic rate limit detection and handling
- **Content Processing**: Automatic markdown processing and content extraction
- **Multi-Content Types**: Support for various file formats and GitHub content types

## Supported Content Types

- Repository files (Markdown, code, documentation)
- GitHub Issues with comments
- Pull Requests with comments
- Various file formats (JSON, YAML, Python, JavaScript, etc.)
- README files and repository metadata

## Setup and Installation

### Requirements

- Dify platform version >= 1.9.0
- Python 3.12+
- Valid GitHub account with appropriate permissions

### Installation

1. Install the plugin in your Dify instance
2. Configure authentication credentials (see Authentication section below)
3. Test the connection and start using GitHub as a datasource

## Authentication

### Option 1: Personal Access Token (Recommended for Development)

1. Go to GitHub Settings > Developer settings > Personal access tokens
2. Click "Generate new token (classic)"
3. Select the following scopes:
   - `repo` - Full control of private repositories
   - `user:email` - Access user email addresses
   - `read:user` - Read user profile data
4. Copy the generated token
5. In Dify, configure the datasource with your token

**Example Configuration:**
```yaml
access_token: "ghp_xxxxxxxxxxxxxxxxxxxx"
```

### Option 2: OAuth (Recommended for Production)

1. Create a GitHub OAuth App:
   - Go to GitHub Settings > Developer settings > OAuth Apps
   - Click "New OAuth App"
   - Fill in application details:
     - Application name: "Dify GitHub Integration"
     - Homepage URL: "https://your-dify-domain.com"
     - Authorization callback URL: "https://your-dify-domain.com/console/api/oauth/callback"
2. Note the Client ID and Client Secret
3. Configure in Dify system settings
4. Users can then authorize through OAuth flow

**System Configuration Example:**
```yaml
client_id: "your_github_client_id"
client_secret: "your_github_client_secret"
```

## Usage Workflows

### 1. Repository Content Access

1. Add GitHub datasource to your Dify knowledge base
2. The plugin will automatically discover your accessible repositories
3. Select repositories, files, issues, or PRs to include
4. Content is automatically processed and indexed

### 2. Issue Tracking Integration

1. Configure GitHub datasource with appropriate permissions
2. Issues and PRs are automatically discovered and indexed
3. Search and query issue content using Dify's AI capabilities
4. Get insights from issue discussions and resolutions

### 3. Documentation Management

1. Connect repository with extensive documentation
2. README files and markdown documents are automatically processed
3. Create AI-powered documentation search and Q&A
4. Keep documentation knowledge base synchronized

## Configuration Examples

### Basic Datasource Configuration

```yaml
# datasources/github.yaml
name: github_datasource
type: online_document
provider: github_datasource
config:
  repositories:
    - "owner/repository-name"
  include_issues: true
  include_prs: true
  max_repositories: 50
```

### Provider Configuration

```yaml
# provider/github.yaml
identity:
  name: github_datasource
  author: langgenius
  label:
    en_US: GitHub
provider_type: online_document
credentials_schema:
  - name: access_token
    type: secret-input
    required: true
    label:
      en_US: Personal Access Token
oauth_schema:
  client_schema:
    - name: client_id
      type: secret-input
      label:
        en_US: Client ID
    - name: client_secret
      type: secret-input
      label:
        en_US: Client Secret
```

## Rate Limits and Performance

### GitHub API Limits

- **Personal Access Token**: 5,000 requests per hour
- **OAuth**: 5,000 requests per hour per user
- **GitHub Apps**: Higher limits available

### Optimization Features

- Automatic rate limit detection and handling
- Intelligent request batching
- Content caching to reduce API calls
- Graceful degradation when limits are reached

## Troubleshooting

### Common Issues

#### "Invalid access token" Error

**Problem**: Authentication fails with token error

**Solution**:
1. Verify token is valid and not expired
2. Check token has required scopes (`repo`, `user:email`, `read:user`)
3. Ensure token hasn't been revoked
4. Generate a new token if needed

#### "Rate limit exceeded" Error

**Problem**: Too many API requests in short time

**Solution**:
1. Wait for rate limit reset (shown in error message)
2. Reduce the number of repositories being accessed
3. Consider using GitHub Apps for higher limits
4. Implement request batching in your usage

#### "Repository not found" Error

**Problem**: Cannot access specific repository

**Solution**:
1. Verify repository name is correct (case-sensitive)
2. Check if repository is private and token has access
3. Ensure token has `repo` scope for private repositories
4. Verify you have read access to the repository

### Debug Mode

Enable debug logging to troubleshoot issues:
```python
import logging
logging.getLogger('datasources.github').setLevel(logging.DEBUG)
```

## FAQ

### Q: Can I access private repositories?
**A**: Yes, with proper Personal Access Token with `repo` scope or OAuth authorization.

### Q: Are GitHub Enterprise repositories supported?
**A**: Currently supports GitHub.com only. Enterprise support may be added in future versions.

### Q: How often is content synchronized?
**A**: Content is fetched in real-time when accessed. No background synchronization is performed.

### Q: What happens if my token expires?
**A**: Personal Access Tokens don't expire unless manually revoked. OAuth tokens are handled automatically.

### Q: Can I limit which repositories are accessible?
**A**: Yes, you can configure specific repositories in the datasource configuration.

## Security Considerations

### Token Management
- Store tokens securely using Dify's encrypted credential storage
- Regularly rotate Personal Access Tokens
- Monitor token usage in GitHub settings
- Use minimal required scopes

### Data Privacy
- Plugin only accesses explicitly authorized content
- No data is stored outside of Dify platform
- All API communications are encrypted with HTTPS
- Follows GitHub's data handling policies

## Support and Community

### Documentation
- [Dify Documentation](https://docs.dify.ai)
- [GitHub API Documentation](https://docs.github.com/en/rest)

### Issues and Feature Requests
- Report issues through Dify support channels
- Feature requests can be submitted via Dify community

### Version History
- **v0.3.0**: Complete OAuth support, Issue/PR access
- **v0.2.0**: Enhanced authentication methods
- **v0.1.0**: Basic repository file access

## Version: 0.3.0

This plugin implements all features up to v0.3.0 including comprehensive OAuth support, advanced content access, and enhanced security measures.
