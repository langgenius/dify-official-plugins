# Salesforce Plugin for Dify

**Author:** langgenius  
**Version:** 0.0.1  
**Type:** Tool Plugin

## Description

The Salesforce Plugin enables seamless integration with Salesforce CRM, allowing AI agents to interact with Salesforce directly from Dify. This plugin provides tools for case management and Chatter messaging functionality.

## Features

- **Case Management**: Create and track customer support cases in Salesforce
- **Chatter Messaging**: Send messages and post updates through Salesforce Chatter
- **Secure Authentication**: Uses username, password, and security token for secure API access
- **Sandbox Support**: Compatible with both production and sandbox environments

## Tools

### 1. Create Case
Creates a new case in Salesforce with customizable fields.

**Parameters:**
- `subject` (required): Brief summary of the case
- `description` (required): Detailed description of the issue
- `priority` (optional): High, Medium, or Low (default: Medium)
- `status` (optional): Case status (default: New)
- `origin` (optional): Channel through which case was created (Phone, Email, Web, Chat)
- `contact_id` (optional): Salesforce Contact ID to associate with the case
- `account_id` (optional): Salesforce Account ID to associate with the case

**Returns:**
- Case ID, Case Number, and full case details

### 2. Send Message
Posts messages through Salesforce Chatter to user feeds, groups, or records.

**Parameters:**
- `message_text` (required): The text content of the message
- `parent_id` (optional): Target User, Group, or Record ID (defaults to current user)
- `feed_type` (optional): TextPost, LinkPost, or ContentPost (default: TextPost)
- `link_url` (optional): URL to share (for LinkPost type)
- `title` (optional): Title for the post

**Returns:**
- Feed Item ID and post details

## Configuration

Before using the plugin, you need to configure your Salesforce credentials:

### Required Credentials:
- **Username**: Your Salesforce account email address
- **Password**: Your Salesforce account password
- **Security Token**: Your Salesforce security token

### Optional Credentials:
- **Domain**: Leave empty for production, or enter 'test' for sandbox environment

### Getting Your Security Token:
1. Log in to Salesforce
2. Navigate to Settings → My Personal Information → Reset My Security Token
3. Click "Reset Security Token"
4. Check your email for the new security token

## Usage Examples

### Creating a Case
```
Create a high-priority case with subject "System outage" and description "The production system is down for all users in the North region"
```

### Posting to Chatter
```
Post a message to Chatter saying "Deployment completed successfully for version 2.0"
```

## API Version

This plugin uses the `simple-salesforce` library version 0.1.45 to interact with Salesforce APIs.

## Troubleshooting

### Authentication Failed
- Verify your username, password, and security token are correct
- Ensure your password + security token are concatenated correctly
- Check if you're using the correct domain (production vs sandbox)

### Permission Denied
- Ensure your Salesforce user has the necessary permissions
- For Chatter functionality, verify Chatter is enabled for your organization
- Check if your user profile has access to the Case object

### Connection Issues
- Verify network connectivity
- Check if your IP address is whitelisted in Salesforce (if IP restrictions are enabled)
- Ensure Salesforce API is available and not under maintenance

## Security

This plugin requires sensitive credentials to function. Always:
- Store credentials securely
- Never commit credentials to version control
- Use environment-specific credentials
- Regularly rotate security tokens
- Follow your organization's security policies

## Support

For issues, questions, or contributions, please contact the plugin author or refer to the Dify Plugin documentation.

## License

Please refer to the LICENSE file for licensing information.

