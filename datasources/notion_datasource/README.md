# Notion Datasource Plugin

**Author**: langgenius  
**Version**: 0.1.11 
**Type**: datasource (online_document)

## Introduction

This plugin integrates with Notion, enabling seamless access to your Notion workspace content within Dify. It allows you to search, retrieve, and process pages and databases from your Notion workspace, making your knowledge base and documentation available for AI applications. The plugin supports both Internal Integration tokens and OAuth authentication for flexible deployment options.

## Features

- **Page and Database Access**: Search and retrieve pages and databases from your Notion workspace
- **Content Extraction**: Extract structured content from Notion pages
- **Flexible Authentication**: Support for both Internal Integration tokens and OAuth
- **Workspace Information**: Access workspace metadata and user information
- **Real-time Sync**: Always get the latest content from your Notion workspace
- **Selective Access**: Control which pages the integration can access
- **Block-level Processing**: Extract content from various Notion block types

## Setup

### Prerequisites

Before using this plugin, you need:
1. A Notion account with workspace access
2. Pages or databases you want to access
3. Admin permissions to create integrations (for Internal Integration method)

### Configuration Methods

You can configure this plugin using either of two methods:

#### Method 1: Internal Integration (Recommended for Private Use)

1. **Create a Notion Integration**:
   - Go to [Notion Integrations](https://www.notion.so/profile/integrations)
   - Click "New integration"
   - Configure your integration:
     - **Name**: e.g., "Dify Plugin"
     - **Associated workspace**: Select your workspace
     - **Capabilities**: Ensure "Read content" is enabled
   - Click "Submit"

2. **Get Your Integration Token**:
   - After creating the integration, you'll see an "Internal Integration Secret"
   - Copy this token (starts with `secret_`)
   - Keep it secure - this is your authentication credential

3. **Share Pages with Your Integration**:
   - Open each Notion page you want to access
   - Click the "..." menu in the top right
   - Select "Add connections"
   - Search for and select your integration
   - The integration now has access to this page and its sub-pages

4. **Configure the Plugin in Dify**:
   - Navigate to the datasource plugins section in Dify
   - Select Notion
   - Enter your **Integration Secret** (the token you copied)
   - Click "Save" to store the configuration

#### Method 2: OAuth Authentication (For Multi-user Applications)

1. **Set Up OAuth Application**:
   - Create a public integration in Notion
   - Configure OAuth settings with appropriate redirect URLs
   - Note your Client ID and Client Secret

2. **Configure OAuth in Dify**:
   - Enter your Client ID and Client Secret
   - Users will be redirected to Notion for authorization
   - Upon approval, they can access their authorized content

## Usage

### Accessing Pages and Databases

Once configured, the plugin can:

1. **List Authorized Content**:
   - Retrieves all pages and databases the integration has access to
   - Displays workspace information and metadata

2. **Extract Page Content**:
   - Fetches full content from specific pages
   - Converts Notion blocks to structured text
   - Preserves formatting and hierarchy

3. **Search Functionality**:
   - Search across authorized pages and databases
   - Filter by page type or properties

### Output Format

The plugin returns structured data for each page:

```json
{
  "workspace_id": "workspace-uuid",
  "page_id": "page-uuid",
  "content": "Extracted and formatted page content..."
}
```

## Supported Notion Block Types

The plugin can extract content from various Notion block types:

- **Text Blocks**: Paragraphs, headings (H1-H3)
- **Lists**: Bulleted lists, numbered lists, toggle lists
- **Databases**: Table views, list views, gallery views
- **Formatting**: Bold, italic, code, links
- **Special Blocks**: Callouts, quotes, dividers
- **Nested Content**: Child pages and nested blocks

## Best Practices

### 1. Page Sharing Strategy

- **Selective Sharing**: Only share pages that should be accessible
- **Hierarchical Access**: Sharing a parent page grants access to all sub-pages
- **Database Access**: Share databases to include all their entries

### 2. Content Organization

- **Structure Your Workspace**: Organize content logically for better retrieval
- **Use Clear Titles**: Page titles become searchable metadata
- **Consistent Formatting**: Helps with content extraction quality

### 3. Security Considerations

- **Token Security**: Never expose your integration token publicly
- **Access Control**: Regularly review which pages are shared
- **Workspace Isolation**: Use separate workspaces for different security levels

### 4. Performance Optimization

- **Batch Operations**: Process multiple pages efficiently
- **Rate Limiting**: The plugin respects Notion's API rate limits
- **Selective Extraction**: Only fetch content when needed

## Common Use Cases

### 1. Knowledge Base Integration
Connect your Notion documentation to create an AI-powered knowledge assistant:
- Company wikis and documentation
- Product specifications
- Standard operating procedures

### 2. Content Management
Use Notion as a content source for AI applications:
- Blog posts and articles
- Marketing content
- Educational materials

### 3. Project Documentation
Access project information for AI-assisted project management:
- Project plans and timelines
- Meeting notes and decisions
- Task lists and requirements

### 4. Personal Assistant
Create a personal AI assistant with access to your notes:
- Personal knowledge management
- Research notes
- Learning materials

## Troubleshooting

### Common Issues

1. **"Access token not found" error**:
   - Verify your Integration Secret is correctly entered
   - Ensure the token hasn't been regenerated in Notion

2. **"Page not found" or empty results**:
   - Check if the integration has access to the pages
   - Verify pages are shared with the integration
   - Ensure the integration is not removed from the workspace

3. **"Permission denied" errors**:
   - Confirm the integration has "Read content" capability
   - Check workspace-level restrictions
   - Verify the page isn't in a restricted area

4. **Rate limiting issues**:
   - The plugin automatically handles rate limits
   - For persistent issues, reduce request frequency
   - Consider upgrading your Notion plan for higher limits

5. **Content extraction problems**:
   - Some complex Notion features may not be fully supported
   - Embedded content might not be extracted
   - Check if the page uses unsupported block types

## Limitations

- **File Attachments**: Media files and attachments are not downloaded
- **Real-time Updates**: Changes in Notion are reflected on next fetch
- **Comments**: Page comments and discussions are not accessible
- **Permissions**: Cannot modify content, read-only access
- **Version History**: Cannot access page history or revisions
- **Private Content**: Cannot access private or draft pages not shared

## API Information

The plugin uses Notion API v1 with version `2022-06-28` for stability:
- **Base URL**: `https://api.notion.com/v1`
- **Authentication**: Bearer token (Integration Secret)
- **Rate Limits**: Subject to Notion's API rate limits

## Security Notes

- All API communications use HTTPS encryption
- Tokens are never logged or exposed in responses
- The plugin follows Notion's security best practices
- No data is cached or stored permanently

## Privacy

Please refer to the [Privacy Policy](PRIVACY.md) for detailed information on how your data is handled when using this plugin.

## Support

For issues or questions:
- **Plugin Support**: [hello@dify.ai](mailto:hello@dify.ai)
- **Notion API Documentation**: [https://developers.notion.com](https://developers.notion.com)
- **Notion Help Center**: [https://www.notion.so/help](https://www.notion.so/help)

## Additional Resources

- [Notion API Reference](https://developers.notion.com/reference)
- [Notion Integration Guide](https://developers.notion.com/docs/getting-started)
- [Notion Security Best Practices](https://www.notion.so/Security-Best-Practices)
- [API Changelog](https://developers.notion.com/changelog)

## Updates and Changelog

**Version 0.1.10** (Current)
- Enhanced page content extraction
- Improved error handling
- Support for more block types
- Better workspace information retrieval

## Tips for Success

1. **Start Small**: Begin with a few pages to test the integration
2. **Document Structure**: Use consistent page structures for better extraction
3. **Regular Reviews**: Periodically review integration access
4. **Monitor Usage**: Track API usage to stay within limits
5. **Backup Important Data**: Keep backups of critical information

Last updated: December 2024
