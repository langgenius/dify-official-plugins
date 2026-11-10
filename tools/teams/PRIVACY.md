# Privacy Policy

## Data Collection

This plugin does not collect personal data of its own. To operate it uses Microsoft OAuth2: you authorize a Microsoft (Azure AD) application, and Dify stores the resulting **access token** and **refresh token**. These are used only to authenticate requests to the Microsoft Graph API.

With the "Each user signs in" authorization, the workspace credential holds only the app registration (tenant ID, client ID, client secret, sign-in callback URL). Each chat user's Microsoft access and refresh tokens, and the account name they signed in with (read once from Microsoft Graph `/me` so the agent can tell them which account is connected), are kept in the plugin's storage in your Dify installation, keyed by a hash of the Dify user ID and encrypted with a key derived from the client secret. During sign-in, the one-time authorization code is held briefly until it is redeemed. Tokens are never returned to the agent or included in tool output.

## Data Processing

When you invoke a tool, the parameters you supply (team/channel/chat/plan/task/meeting IDs, message text, task and meeting details, user IDs or user principal names of chat members and task assignees) and, for reads, the data returned by Microsoft Graph (teams, channels, chats and their members, messages and replies, online meetings, Planner plans, buckets and tasks) are sent directly between Dify and Microsoft Graph to perform the requested action. The plugin acts only as a pass-through and does not retain this data after a request completes. Because it uses delegated permissions, actions are performed as the signed-in user.

## Third-party Services

This plugin communicates with **Microsoft Graph / Microsoft 365** (https://graph.microsoft.com, or the national-cloud endpoint selected in the plugin settings). Your use of Microsoft services is governed by the Microsoft Privacy Statement: https://privacy.microsoft.com/privacystatement

## Data Retention

OAuth tokens are retained by your Dify instance for as long as the plugin is configured, and access tokens are refreshed automatically. With "Each user signs in", a user's tokens are kept until the user signs out (Sign Out tool), the refresh token stops working, or the client secret is rotated. Messages and other content are subject to Microsoft's own retention policies.

## User Rights

Requests regarding data access, correction, or deletion should be directed to your Dify administrator (for stored tokens; with "Each user signs in", a user can also remove their own with the Sign Out tool) and to Microsoft (for data held in your Microsoft 365 tenant).

## Contact Information

For privacy-related questions about this plugin, please contact the plugin author via the Dify Marketplace listing.

Last updated: 2026-11-01
