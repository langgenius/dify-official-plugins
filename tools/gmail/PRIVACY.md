# Privacy Policy

## Data Collection
This plugin requires Google OAuth 2.0 credentials (client ID and client secret) to authenticate with Gmail API. These credentials are used solely for the purpose of accessing your Gmail account.

## Data Processing
- All email operations (reading, sending, listing, drafting) are performed through Gmail API
- Your OAuth credentials are stored securely and are only used to authenticate API requests
- No email content or metadata is stored by this plugin
- In the "Each user signs in" mode, each user's Google tokens and the email of the account they signed in with are kept in the plugin's storage in your Dify instance, encrypted with a key derived from the OAuth client secret (see Data Retention)
- All operations are performed in real-time and no data is cached
- The plugin only accesses Gmail data when you explicitly use the tools

## Third-party Services
This plugin uses the following third-party services:
- Gmail API: For accessing Gmail email functionality
- Google OAuth 2.0: For authentication and authorization
- Google Cloud Console: For managing OAuth application credentials

## Data Retention
- Apart from the per-user sign-ins below, no data is retained by this plugin
- "Each user signs in" mode:
  - Per user: that user's access and refresh tokens and their account email.
  - While a sign-in is in progress: a random state, a PKCE verifier and, briefly, the one-time authorization code.
  - These are encrypted with a key derived from the client secret and never shown in tool output.
  - One user's sign-in is removed when they ask the agent to sign out (`gmail_sign_out`). Changing the client secret makes every stored sign-in unreadable.
- All operations are performed in real-time
- Your Google OAuth credentials are stored securely in your Dify workspace
- No email content, attachments, or metadata are stored locally

## Gmail API Scopes
This plugin requests the following Gmail API scopes:
- `gmail.readonly`: Read access to your emails
- `gmail.send`: Send emails on your behalf
- `gmail.compose`: Create and modify draft emails
- `gmail.modify`: Modify emails (labels, flags, etc.)
- `gmail.labels`: Manage Gmail labels

## User Rights
You have the right to:
- Revoke access to your Gmail account at any time through Google Account settings
- Delete your Google OAuth application credentials
- Request information about how your data is being used
- Control which Gmail API scopes are granted to the application

## Security
- All communication with Gmail API is encrypted using HTTPS
- OAuth tokens are stored securely in your Dify workspace; per-user tokens are encrypted in the plugin's storage
- No sensitive data is logged or transmitted to third parties
- The plugin follows Google's security best practices for OAuth 2.0

## Contact Information
For privacy-related inquiries, please contact the plugin author at support@langgenius.ai

Last updated: 2026-11-02