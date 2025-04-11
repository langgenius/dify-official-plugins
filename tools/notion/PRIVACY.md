# Privacy Policy - Notion Plugin for Dify

## Data Collection

The Notion Plugin for Dify collects the following information:
- Your Notion Integration Token (securely encrypted)
- Notion page, database, and content IDs that you interact with
- Search queries and filter criteria you provide when using the plugin
- Content you create or update through the plugin

## Data Processing

### How We Use Your Data
- To authenticate with the Notion API on your behalf
- To execute the specific operations you request (search, query, create/update pages, retrieve content)
- To display relevant results within your Dify applications
- To process page and database content for display and interaction

### Where Your Data is Stored
- Your Notion Integration Token is stored securely and encrypted in Dify's credential storage
- No content from your Notion workspace is permanently stored by the plugin itself
- All Notion API requests are processed directly between the plugin and Notion's servers
- API responses containing page or database content are temporarily cached in memory during processing

## Third-party Services

This plugin uses the following third-party services:
- **Notion API**: All interactions with your Notion workspace are conducted through the official [Notion API](https://developers.notion.com/). Please refer to Notion's [Privacy Policy](https://www.notion.so/Privacy-Policy-3468d120cf614d4c9014c09f6adc9091) for information on how Notion handles your data.

## Data Retention

- Your Notion Integration Token is retained for as long as you have the plugin installed
- Query logs may be temporarily stored for debugging purposes for up to 30 days
- No permanent storage of your Notion content occurs within the plugin
- API cache is cleared at the end of each request session

## User Rights

You have the right to:
- Uninstall the plugin at any time, which will remove your stored credentials
- Request information about what data has been processed through the plugin
- Request deletion of any logs or data related to your usage of the plugin
- Control which pages and databases the integration has access to through Notion's sharing settings

## Security Measures

- The plugin implements proper rate limiting handling to prevent overuse of your account
- API requests use secure HTTPS connections
- Error handling is designed to prevent exposing sensitive information
- No plain text storage of your integration token

## Contact Information

For privacy-related inquiries regarding this plugin, please contact:
[support@dify.ai](mailto:support@dify.ai)

Last updated: April 11, 2024