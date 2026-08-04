# Privacy Policy

## Data Collection

This plugin does not collect or store personal data of its own. To operate it uses Microsoft OAuth2: you authorize a Microsoft (Azure AD) application, and Dify stores the resulting **access token** and **refresh token**. These are used only to authenticate requests to the Microsoft Graph API.

## Data Processing

When you invoke a tool, the parameters you supply (team/channel/chat IDs, message text) and, for reads, the data returned by Microsoft Graph (teams, channels, chats, messages) are sent directly between Dify and Microsoft Graph to perform the requested action. The plugin acts only as a pass-through and does not retain this data after a request completes. Because it uses delegated permissions, actions are performed as the signed-in user.

## Third-party Services

This plugin communicates with **Microsoft Graph / Microsoft 365** (https://graph.microsoft.com). Your use of Microsoft services is governed by the Microsoft Privacy Statement: https://privacy.microsoft.com/privacystatement

## Data Retention

The plugin itself retains no data. OAuth tokens are retained by your Dify instance for as long as the plugin is configured, and access tokens are refreshed automatically. Messages and other content are subject to Microsoft's own retention policies.

## User Rights

Because the plugin stores no data of its own, requests regarding data access, correction, or deletion should be directed to your Dify administrator (for stored tokens) and to Microsoft (for data held in your Microsoft 365 tenant).

## Contact Information

For privacy-related questions about this plugin, please contact the plugin author via the Dify Marketplace listing.

Last updated: 2026-08-04
