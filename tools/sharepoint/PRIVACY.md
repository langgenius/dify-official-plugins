# Privacy Policy

**Effective Date: November 1, 2026**

This Privacy Policy explains how the Microsoft SharePoint plugin for Dify handles your information.

## Information Collection

The plugin does not collect personal information of its own. It sends the inputs of the operation you run (site, list, item and file identifiers, item field values, file contents and names) to Microsoft Graph, and returns what Microsoft Graph sends back (sites, lists and their columns, list items, file metadata and contents) to your Dify workflow or agent.

## Data Storage

The plugin does not keep SharePoint content after a request completes. Credentials are stored as follows:

- **OAuth**: the access and refresh tokens are stored by your Dify workspace.
- **Service Principal**: the tenant ID, client ID and client secret are stored by your Dify workspace; the short-lived app token is kept in the plugin process's memory until it expires.
- **Each user signs in**: the workspace credential holds only the app registration (tenant ID, client ID, client secret, sign-in callback URL). Each chat user's Microsoft access and refresh tokens, and the account name they signed in with (read once from Microsoft Graph `/me` so the agent can tell them which account is connected), are kept in the plugin's storage in your Dify installation, keyed by a hash of the Dify user ID and encrypted with a key derived from the client secret. During sign-in, the one-time authorization code is held briefly until it is redeemed. A user's tokens are kept until the user signs out (Sign Out of SharePoint tool), the refresh token stops working, or the client secret is rotated.

Tokens are never returned to the agent or included in tool output or error messages.

## Third-Party Services

This plugin communicates with Microsoft Graph (graph.microsoft.com, or the national-cloud endpoint selected in the plugin settings) and signs in through Microsoft Entra ID. File downloads use the short-lived, pre-authenticated link Microsoft Graph returns; no token is sent with them. Your use of Microsoft services is governed by the Microsoft Privacy Statement: https://privacy.microsoft.com/privacystatement

## Your Rights

Requests about stored credentials go to your Dify administrator; a user can also remove their own sign-in with the Sign Out of SharePoint tool. An administrator can revoke access at any time in Microsoft Entra ID. Data in SharePoint is subject to your organization's Microsoft 365 policies.

## Contact

For privacy questions about this plugin, contact [hello@dify.ai](mailto:hello@dify.ai) or open an issue in the plugin repository.

Last updated: November 1, 2026
