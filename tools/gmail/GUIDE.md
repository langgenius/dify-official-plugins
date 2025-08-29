# Gmail Plugin Setup Guide

This guide will walk you through setting up the Gmail plugin for Dify step by step.

## Prerequisites

- A Google account with Gmail access
- Access to Google Cloud Console

## Step 1: Install Gmail Plugin from Dify Marketplace

1. Go to your Dify workspace
2. Navigate to "Plugin Management" or "Marketplace"
3. Search for "Gmail" or "dify-gmail"
4. Click "Install" on the Gmail plugin
5. The plugin will be added to your workspace

## Step 2: Obtain Dify OAuth Callback URL

1. In the installed Gmail plugin, go to "OAuth Client Settings" or "Configuration"
2. Look for the "Callback URL" or "Redirect URI" field
3. Copy this URL - you'll need it for Google Cloud Console setup
4. **Note**: Keep this URL handy as you'll need to paste it into Google Cloud Console

## Step 3: Create Google OAuth Client with Gmail API

### 3.1 Go to Google Cloud Console

1. Visit [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Make sure you're in the correct project

### 3.2 Enable Gmail API

1. In the left sidebar, go to "APIs & Services" > "Library"
2. Search for "Gmail API"
3. Click on "Gmail API" and click "Enable"

### 3.3 Configure OAuth Consent Screen

1. Go to "APIs & Services" > "OAuth consent screen"
2. Choose "External" user type
3. Fill in required information:
   - **App name**: "Dify Gmail Plugin"
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
4. Click "Save and Continue"
5. Skip adding scopes for now
6. Add your email as a test user
7. Click "Save and Continue"

### 3.4 Create OAuth 2.0 Client ID

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth 2.0 Client IDs"
3. Choose "Web application"
4. Give it a name like "Dify Gmail Plugin Client"
5. **Important**: In "Authorized redirect URIs", paste the Dify callback URL from Step 2
6. Click "Create"
7. **Save your Client ID and Client Secret** - you won't be able to see the secret again after the first setup

## Step 4: Configure Dify OAuth Client

1. Return to your Dify workspace and the Gmail plugin
2. In the plugin configuration, enter:
   - **Client ID**: The Client ID from Google Cloud Console
   - **Client Secret**: The Client Secret from Google Cloud Console
3. Click "Save" or "Configure"
4. Click "Authorize" or "Connect Gmail"
5. Complete the Google OAuth flow
6. Grant all requested permissions when prompted

**Note**: The plugin will request comprehensive Gmail permissions including reading, sending, composing, and managing emails. This is normal and required for full functionality.

### Getting Additional Help

1. **Check Google Cloud Console**: Verify your API is enabled and credentials are correct
2. **Review OAuth Consent Screen**: Ensure it's properly configured
3. **Check Dify Logs**: Look for detailed error messages in your Dify instance
4. **Google Support**: For Gmail API specific issues, check [Google's API documentation](https://developers.google.com/gmail/api)

## Security Considerations

### OAuth Scopes

The plugin requests the following Gmail permissions:
- **Read emails**: Access to read your email content
- **Send emails**: Ability to send emails on your behalf
- **Manage drafts**: Create and modify draft emails
- **Modify emails**: Change labels and flags
- **Manage labels**: Create and modify Gmail labels

### Best Practices

1. **Regular Review**: Periodically review the OAuth apps in your Google account
2. **Limited Access**: Only grant the permissions you actually need
3. **Secure Storage**: Keep your Client ID and Client Secret secure
4. **Monitor Usage**: Check your Google Cloud Console for API usage statistics

## Next Steps

Once the plugin is configured and working:

1. **Explore Tools**: Try different tools to understand their capabilities
2. **Create Workflows**: Build Dify workflows that integrate Gmail actions
3. **Customize**: Modify the plugin configuration based on your needs
4. **Monitor**: Keep an eye on API usage and performance

## Support

If you continue to have issues:

1. Check the main README.md for detailed tool documentation
2. Review the error messages carefully - they often contain specific guidance
3. Ensure you've followed all steps in this guide exactly
4. Consider reaching out to the Dify community for additional support

---

**Note**: This plugin requires periodic re-authorization as OAuth tokens expire. This is a security feature and normal behavior. 