# Privacy Policy

## Data Collection
This plugin requires Azure AD application credentials (client ID, client secret, and tenant ID) to authenticate with Microsoft Graph API, either through a user's OAuth sign-in, as a Service Principal (app-only), or with each chat user signing in with their own account ("Each user signs in"). With a Service Principal it also stores the default mailbox to act on. These credentials are used solely for the purpose of accessing the configured Outlook mailbox.

## Data Processing
- All email operations (reading, sending, listing) are performed through Microsoft Graph API
- Your credentials are stored securely and are only used to authenticate API requests
- No email content or metadata is stored by this plugin
- All operations are performed in real-time and no email data is cached
- With a Service Principal, the short-lived access token issued by Microsoft Entra ID is kept in the plugin process's memory until it expires, so that consecutive tool calls do not sign in again
- With "Each user signs in", each user's Microsoft access and refresh tokens, and the account name they signed in with (read once from Microsoft Graph `/me` so the agent can tell them which account is connected), are kept in the plugin's storage in your Dify installation, keyed by a hash of the Dify user ID and encrypted with a key derived from the client secret. During sign-in, the one-time authorization code is held briefly until it is redeemed. Tokens are never returned to the agent or included in tool output

## Third-party Services
This plugin uses the following third-party services:
- Microsoft Graph API: For accessing Outlook email functionality
- Azure Active Directory: For authentication and authorization

## Data Retention
- No email or calendar data is retained by this plugin; all operations are performed in real-time
- In "Each user signs in" mode, a user's tokens are kept until the user signs out (Sign Out tool), the refresh token stops working, or the client secret is rotated
- Your Azure AD credentials are stored securely in your Dify workspace

## User Rights
You have the right to:
- Revoke access to your Outlook account at any time (in Microsoft account settings, or with the Sign Out tool in "Each user signs in" mode)
- Delete your Azure AD application credentials
- Request information about how your data is being used

## Contact Information
For privacy-related inquiries, please contact the plugin author at support@langgenius.ai

Last updated: 2026-10-27