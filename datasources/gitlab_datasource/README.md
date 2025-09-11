# GitLab Datasource Plugin

A comprehensive Dify datasource plugin that enables seamless integration with GitLab, allowing you to access projects, issues, merge requests, and files from both GitLab.com and self-hosted GitLab instances.

## 🚀 Features

### Core Functionality
- **🏗️ Project Access**: Browse and download files from public and private projects
- **🎯 Issues & Merge Requests**: Access issue and MR content with full comment threads
- **📁 File Management**: Access any file in your GitLab projects with automatic content processing
- **🔍 Smart Content Processing**: Automatic markdown rendering and content extraction
- **⚡ Real-time Updates**: Access the latest project activity and content

### Authentication & Security
- **🔐 Multiple Authentication Methods**: 
  - Personal Access Tokens (PAT)
  - OAuth 2.0 with automatic refresh
- **🌐 Self-hosted Support**: Full compatibility with self-hosted GitLab instances
- **🛡️ Secure Credential Handling**: Encrypted storage and transmission of credentials
- **🚦 Rate Limit Management**: Intelligent rate limit detection and automatic retry

### Advanced Features
- **📊 Metadata Extraction**: Comprehensive project, issue, and MR metadata
- **💬 Comment Threading**: Full access to discussion threads and notes
- **🏷️ Label & Tag Support**: Access to project labels and categorization
- **🌳 Branch Navigation**: Support for different branches and file versions
- **📈 Activity Tracking**: Access to project activity and timeline data

## 📋 Supported Content Types

### Project Files
- **Documentation**: Markdown (`.md`), reStructuredText (`.rst`), AsciiDoc (`.adoc`)
- **Code Files**: Python (`.py`), JavaScript (`.js`), TypeScript (`.ts`), Java (`.java`), C++ (`.cpp`), and more
- **Configuration**: YAML (`.yaml`, `.yml`), JSON (`.json`), XML (`.xml`), TOML (`.toml`)
- **Data**: CSV (`.csv`), SQL (`.sql`), notebooks (`.ipynb`)
- **Web**: HTML (`.html`), CSS (`.css`), SCSS (`.scss`)

### GitLab Content
- **Projects**: Complete project information, README files, and repository structure
- **Issues**: Issue descriptions, comments, labels, assignees, and status tracking
- **Merge Requests**: MR descriptions, discussions, file changes, and approval status
- **Wiki Pages**: Project wiki content and documentation
- **Snippets**: Code snippets and gists

## 🛠️ Installation

### Prerequisites
- Dify platform (version 1.0.0 or higher)
- GitLab account with appropriate permissions
- Python 3.12+ environment

### Quick Setup

1. **Install the Plugin**
   ```bash
   # Download and install the plugin package
   dify-plugin install gitlab-datasource.difypkg
   ```

2. **Configure Authentication**
   Choose one of the following authentication methods:

   **Option A: Personal Access Token (Recommended for development)**
   - Go to GitLab → Settings → Access Tokens
   - Create a new token with scopes: `read_user`, `read_repository`, `api`
   - Copy the token for configuration

   **Option B: OAuth 2.0 (Recommended for production)**
   - Go to GitLab → Settings → Applications
   - Create a new application with redirect URI from Dify
   - Note the Client ID and Client Secret

## ⚙️ Configuration

### Personal Access Token Setup

1. In Dify, navigate to **Settings** → **Datasources**
2. Find **GitLab** and click **Connect**
3. Choose **Personal Access Token** authentication
4. Fill in the configuration:
   ```
   Personal Access Token: glpat-xxxxxxxxxxxxxxxxxxxx
   GitLab URL: https://gitlab.com (or your self-hosted URL)
   ```

### OAuth 2.0 Setup

1. **GitLab Application Configuration**:
   ```
   Name: Dify GitLab Integration
   Redirect URI: https://your-dify-instance.com/console/api/oauth/callback
   Scopes: read_user read_repository api
   ```

2. **Dify Configuration**:
   ```
   Client ID: your-gitlab-client-id
   Client Secret: your-gitlab-client-secret
   GitLab URL: https://gitlab.com (or your self-hosted URL)
   ```

### Self-hosted GitLab

For self-hosted GitLab instances:
```
GitLab URL: https://gitlab.your-company.com
Personal Access Token: glpat-xxxxxxxxxxxxxxxxxxxx
```

## 📖 Usage Examples

### Basic Project Access
```python
# Access project README
project_readme = datasource.get_content("project:username/project-name")

# Access specific file
file_content = datasource.get_content("file:username/project-name:path/to/file.md")
```

### Issue and MR Access
```python
# Get issue with comments
issue_data = datasource.get_content("issue:username/project-name:123")

# Get merge request with discussions
mr_data = datasource.get_content("mr:username/project-name:456")
```

### Advanced Filtering
```python
# Get recent issues
recent_issues = datasource.get_pages({
    "project_filter": "username/project-name",
    "content_type": "issues",
    "limit": 10,
    "state": "opened"
})
```

## 🔧 API Reference

### Content Types

| Type | Format | Description |
|------|--------|-------------|
| `project` | `project:namespace/project-name` | Complete project information and README |
| `file` | `file:namespace/project-name:file/path` | Individual file content |
| `issue` | `issue:namespace/project-name:issue-iid` | Issue with comments and metadata |
| `mr` | `mr:namespace/project-name:mr-iid` | Merge request with discussions |

### Response Format

```json
{
  "content": "Processed file content or information",
  "title": "Content title",
  "project": "namespace/project-name",
  "type": "project|file|issue|mr",
  "metadata": {
    "url": "https://gitlab.com/...",
    "last_updated": "2024-01-01T00:00:00Z",
    "author": "username",
    "labels": ["bug", "enhancement"]
  }
}
```

## 🚨 Troubleshooting

### Common Issues

**Authentication Failed (401)**
```
Error: Invalid GitLab access token
Solution: Verify your token is valid and has required scopes
```

**Rate Limit Exceeded (429)**
```
Error: GitLab API rate limit exceeded
Solution: Wait for the specified retry time or upgrade GitLab plan
```

**Project Not Found (404)**
```
Error: Project 'namespace/project' not found
Solution: Check project name and ensure you have access permissions
```

**Self-hosted GitLab Issues**
```
Error: Failed to connect to GitLab instance
Solution: Verify GitLab URL format and network connectivity
```

### Debugging

Enable debug logging:
```python
import logging
logging.getLogger("gitlab_datasource").setLevel(logging.DEBUG)
```

### Permission Requirements

**Minimum Required Scopes:**
- `read_user`: Access user profile information
- `read_repository`: Access project files and metadata
- `api`: Access issues, merge requests, and other API endpoints

**For Private Projects:**
- Ensure token/OAuth app has access to private repositories
- Verify project membership and role permissions

## 🔒 Security Considerations

### Token Security
- Use Personal Access Tokens with minimal required scopes
- Regularly rotate access tokens (recommended: every 90 days)
- Monitor token usage in GitLab audit logs

### Network Security
- Use HTTPS for all GitLab communications
- For self-hosted instances, ensure proper SSL/TLS configuration
- Consider IP whitelisting for enhanced security

### Data Privacy
- Plugin accesses only explicitly requested content
- No persistent storage of GitLab credentials
- All data transmission is encrypted
- See [PRIVACY.md](PRIVACY.md) for detailed privacy policy

## 🎯 Performance Optimization

### Caching Strategy
- Content is cached temporarily to reduce API calls
- Metadata caching for improved response times
- Automatic cache invalidation on content updates

### Rate Limit Management
- Intelligent request batching
- Automatic retry with exponential backoff
- Rate limit monitoring and alerts

### Large Project Handling
- Efficient pagination for large project listings
- Streaming for large file downloads
- Memory-efficient processing for bulk operations

## 🔄 Version History

### v0.3.0 (Current)
- ✅ OAuth 2.0 authentication support
- ✅ Self-hosted GitLab compatibility
- ✅ Enhanced merge request support
- ✅ Improved error handling and debugging
- ✅ Advanced metadata extraction

### v0.2.0
- ✅ Issue and merge request access
- ✅ Comment thread support
- ✅ File content extraction
- ✅ Basic project browsing

### v0.1.0
- ✅ Initial release
- ✅ Personal Access Token authentication
- ✅ Basic project access
- ✅ Simple file retrieval

## 📞 Support

### Documentation
- [Dify Documentation](https://docs.dify.ai)
- [GitLab API Documentation](https://docs.gitlab.com/ee/api/)
- [Plugin Development Guide](https://docs.dify.ai/plugins)

### Community Support
- [Dify Discord](https://discord.gg/dify)
- [GitHub Issues](https://github.com/langgenius/dify/issues)
- [Community Forum](https://community.dify.ai)

### Enterprise Support
For enterprise installations and custom requirements:
- Email: enterprise@dify.ai
- Professional services available for custom integrations

## 📄 License

This plugin is released under the MIT License. See [LICENSE](LICENSE) for details.

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

---

**Made with ❤️ for the Dify community**

