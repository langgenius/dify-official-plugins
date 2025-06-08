# Outlook Plugin for Dify

**Author:** langgenius
**Version:** 0.0.1
**Type:** Plugin

## Description
This plugin enables Dify to interact with Microsoft Outlook emails. It provides functionality to list, read, and send emails through the Microsoft Graph API.

## Features
- List messages from your Outlook inbox
- Get detailed information about specific messages
- Send new email messages
- Support for HTML and plain text email content
- Support for CC recipients
- Search and filter messages

## Installation
1. Create an Azure AD application:
   - Go to Azure Portal > App Registrations
   - Create a new registration
   - Add Microsoft Graph API permissions:
     - Mail.Read
     - Mail.Send
   - Create a client secret
   - Note down the client ID, client secret, and tenant ID

2. Install the plugin in Dify:
   - Go to your Dify workspace
   - Navigate to Tools > Plugins
   - Click "Add Plugin"
   - Select this Outlook plugin
   - Enter your Azure AD credentials:
     - Client ID
     - Client Secret
     - Tenant ID

## Usage Examples

### List Messages
```
List the last 10 messages from my inbox
```

### Search Messages
```
Find emails from john@example.com in my inbox
```

### Read Message
```
Get the details of message with ID abc123
```

### Send Message
```
Send an email to john@example.com with subject "Meeting" and body "Let's meet tomorrow"
```

## Configuration
The plugin requires the following Azure AD application permissions:
- Mail.Read: For reading emails
- Mail.Send: For sending emails

## Troubleshooting
1. Authentication Issues:
   - Verify your Azure AD credentials
   - Check if your application has the required permissions
   - Ensure your client secret hasn't expired

2. API Errors:
   - Check your internet connection
   - Verify your Outlook account is accessible
   - Ensure you have the necessary permissions

## Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

## License
This project is licensed under the MIT License - see the LICENSE file for details.



