# Dify Gmail Plugin

A comprehensive Gmail integration plugin for Dify that provides essential mail-related actions using OAuth2.0 authentication. This plugin extends beyond basic email reading to offer a complete Gmail management solution.

## Features

### **Email Management**
- **Get Message Details**: Retrieve detailed information about specific emails including headers, body, and attachments
- **Search Messages**: Advanced Gmail search using Gmail's powerful search syntax and operators

### **Email Composition & Sending**
- **Send Message**: Send emails directly with recipients, subject, body, CC, BCC, and reply-to
- **Create Drafts**: Create draft emails that can be edited and sent later
- **List Drafts**: View and manage draft emails
- **Send Drafts**: Send previously created draft emails

### **Attachment Support**
- **Add Attachments**: Attach files to existing draft emails

### **Email Organization**
- **Flag Messages**: Mark emails for follow-up using Gmail's starring system (adds/removes 'STARRED' label)

## Gmail Search Operators

The plugin supports Gmail's powerful search syntax:

- **Sender/Recipient**: `from:example@gmail.com`, `to:colleague@company.com`
- **Subject**: `subject:meeting`, `subject:"project update"`
- **Date Ranges**: `after:2024/01/01`, `before:2024/12/31`
- **Status**: `is:unread`, `is:read`, `is:starred`, `is:important`
- **Attachments**: `has:attachment`, `filename:pdf`
- **Size**: `larger:10M`, `smaller:1M`
- **Labels**: `label:work`, `label:personal`
- **Combined**: `from:boss@company.com subject:meeting after:2024/01/01 has:attachment`

## Setup Instructions

**For detailed setup instructions, see [GUIDE.md](GUIDE.md)**

### Quick Setup Overview

1. **Install the plugin** from Dify Marketplace
2. **Get the OAuth callback URL** from the plugin's OAuth Client Settings
3. **Create Google OAuth credentials** with Gmail API enabled, using the Dify callback URL
4. **Configure the plugin** with your Client ID and Client Secret

### Required OAuth Scopes

The plugin requests the following Gmail API scopes:
- `https://www.googleapis.com/auth/gmail.readonly` - Read emails
- `https://www.googleapis.com/auth/gmail.send` - Send emails
- `https://www.googleapis.com/auth/gmail.compose` - Create drafts
- `https://www.googleapis.com/auth/gmail.modify` - Modify emails (labels, flags)
- `https://www.googleapis.com/auth/gmail.labels` - Manage labels

## Usage Examples

### List Recent Inbox Messages
```yaml
tool: search_messages
parameters:
  query: "in:inbox"
  max_results: 10
  include_body: false
```

### Search for Important Emails
```yaml
tool: search_messages
parameters:
  query: "is:important subject:urgent after:2024/01/01"
  max_results: 20
  include_body: true
```

### Send an Email
```yaml
tool: send_message
parameters:
  to: "recipient@example.com"
  subject: "Meeting Reminder"
  body: "Hi, this is a reminder about our meeting tomorrow."
  cc: "manager@example.com"
```

### Create a Draft
```yaml
tool: draft_message
parameters:
  to: "team@company.com"
  subject: "Weekly Update"
  body: "Here's our weekly team update..."
```

### Flag a Message for Follow-up
```yaml
tool: flag_message
parameters:
  message_id: "18c1a2b3d4e5f6g7"
  action: "flag"
```

## Tool Reference

### Core Tools

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `search_messages` | Advanced Gmail search | `query`, `max_results`, `include_body` |
| `get_message` | Get detailed message information | `message_id`, `include_body` |

### Email Composition

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `send_message` | Send email immediately | `to`, `subject`, `body`, `cc`, `bcc`, `reply_to` |
| `draft_message` | Create draft email | `to`, `subject`, `body`, `cc`, `bcc`, `reply_to` |
| `list_drafts` | List draft emails | `max_results`, `include_body` |
| `send_draft` | Send draft email | `draft_id` |

### Advanced Features

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `add_attachment_to_draft` | Add file to draft | `draft_id`, `file_path` |
| `flag_message` | Flag/unflag for follow-up | `message_id`, `action` |

## Error Handling

The plugin provides comprehensive error handling:

- **Authentication Errors**: Clear messages when OAuth tokens expire
- **API Errors**: Detailed error messages from Gmail API
- **Validation Errors**: Parameter validation with helpful suggestions
- **File Errors**: Clear messages for file access and size issues

## Limitations

- **File Attachments**: Subject to Gmail API file size limitations
- **Rate Limits**: Subject to Gmail API rate limits
- **Authentication**: Requires OAuth2.0 setup and periodic token refresh
- **Search Queries**: Limited to Gmail's search syntax and operators

## Troubleshooting

### Common Issues

1. **"Access token expired"**: Re-authorize the plugin in Dify
2. **"File not found"**: Ensure the file path is accessible from the plugin environment
3. **"Draft not found"**: Verify the draft ID is valid and hasn't been deleted
4. **"Permission denied"**: Check that all required Gmail scopes are granted

### Getting Help

- Check the Gmail API documentation for detailed error codes
- Verify your OAuth2.0 credentials are correct
- Ensure the Gmail API is enabled in your Google Cloud project

## Development

This plugin is built using the Dify plugin framework and follows best practices:

- **Modular Design**: Each tool is implemented as a separate class with clear separation of concerns
- **Error Handling**: Comprehensive error handling with user-friendly error messages
- **Progress Updates**: Real-time progress updates for operations involving multiple emails
- **OAuth2.0 Integration**: Secure authentication with automatic token refresh
- **Gmail API Integration**: Direct integration with Gmail API for optimal performance

## License

This plugin is provided as-is for use with Dify. Please refer to Dify's licensing terms for usage rights. 