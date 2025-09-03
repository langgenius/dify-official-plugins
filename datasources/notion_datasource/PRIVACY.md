# Privacy Policy

This Privacy Policy explains how we collect, use, and protect your information when you use the Notion Datasource Plugin for Dify.

## Information Collection

We do not collect, store, or share any personal information from users. All data processed by the plugin is handled locally or through secure connections to Notion API services, as required for functionality.

## Use of Information

The plugin only accesses your Notion workspace content to provide the requested features:
- Searching and retrieving pages from your Notion workspace
- Accessing databases and their content
- Extracting page content in structured format
- Listing authorized pages and databases

No personal data is collected, stored, or transmitted to third parties by the plugin itself.

## Data Processing

When using this plugin:
- **Workspace Access**: Only accesses pages and databases you've explicitly authorized
- **Content Extraction**: Page content is extracted and converted to structured text
- **Real-time Processing**: Data is processed on-demand and not permanently cached
- **Limited Scope**: Only accesses content within the permissions granted to the integration

## Third-Party Services

This plugin interacts with Notion API services:
- **API Endpoint**: `https://api.notion.com/v1`
- **OAuth Endpoints**: Used for authentication when using OAuth flow
- Please refer to [Notion's Privacy Policy](https://www.notion.so/Privacy-Policy) for details on how your data is handled by Notion

## Authentication Methods

### Integration Token (Internal Integration)
- Token is created and managed within your Notion workspace
- Full control over which pages the integration can access
- Token is transmitted securely via HTTPS
- Token is only stored for the duration of your session

### OAuth Authentication
- Uses Notion's official OAuth 2.0 flow
- Client credentials are handled securely
- Access tokens are session-based
- Refresh tokens can be used to maintain access

## Data Security

We are committed to ensuring the security of your data:
- All communications with Notion API use secure HTTPS protocols
- Authentication tokens are transmitted securely
- No workspace content is permanently stored by the plugin
- API version locking ensures consistent behavior
- Rate limiting is respected to prevent service disruption

## Data Access Scope

The plugin requires the following Notion permissions:
- **Read content**: Access to read pages and databases
- **Read user information**: Basic workspace and user info
- **Search**: Ability to search within authorized content

The plugin does NOT:
- Modify or delete any content in your Notion workspace
- Access pages not explicitly shared with the integration
- Store your Notion content permanently
- Share your data with unauthorized third parties

## User Control

You have complete control over:
- Which pages and databases the integration can access
- When to grant or revoke access permissions
- Which workspace to connect
- The scope of content accessible to the plugin

### Managing Permissions

**For Internal Integrations:**
1. Go to your Notion workspace settings
2. Navigate to "My integrations"
3. Manage page-level permissions
4. Revoke access at any time

**For OAuth Connections:**
1. Access your Notion settings
2. Review connected applications
3. Revoke OAuth access when needed

## Content Types Processed

The plugin processes:
- Page content (text, headings, lists, etc.)
- Database properties and entries
- Blocks (paragraphs, bullets, toggles, etc.)
- Page metadata (title, last edited, etc.)

The plugin does NOT process:
- File attachments or media files
- Comments and discussions
- Version history
- Private or draft content not shared with the integration

## Compliance

This plugin respects:
- Notion's API terms of service
- Workspace-level permissions and restrictions
- User privacy settings
- Data protection regulations

## Data Retention

- **No Permanent Storage**: The plugin does not retain Notion content after processing
- **Session Data**: Temporary data is cleared after each session
- **Authentication Tokens**: Stored only for active sessions
- **Cache**: No caching of workspace content is performed

## Children's Privacy

This plugin does not knowingly collect or process data from children under 13 years of age.

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Your Rights

You have the right to:
- Know what data is being accessed
- Control integration permissions
- Revoke access at any time
- Request information about data processing
- Report privacy concerns

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: December 2024
