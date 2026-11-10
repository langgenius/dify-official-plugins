
# Privacy Policy

**Effective Date: July 18, 2025**

This Privacy Policy explains how we collect, use, and protect your information when you use the Microsoft To Do Plugin for Dify.

## Information Collection

We do not collect or share any personal information from users, and store only the sign-in data described under Data Security. All data processed by the plugin is handled locally or through secure connections to Microsoft services, as required for functionality.

## Use of Information

The plugin only accesses your Microsoft To Do data to provide the requested features, such as viewing, creating, or completing tasks. No data is stored or transmitted to third parties by the plugin itself.

## Data Security

We are committed to ensuring the security of your data. All communications with Microsoft services use secure protocols (such as HTTPS). We do not retain task data beyond a request. Credentials (OAuth tokens, or the tenant ID, client ID, client secret and default task owner of a Service Principal) are stored by your Dify workspace; with a Service Principal, the short-lived app token is kept in the plugin process's memory until it expires.

With "Each user signs in", the workspace credential holds only the app registration (tenant ID, client ID, client secret, sign-in callback URL). Each chat user's Microsoft access and refresh tokens, and the account name they signed in with (read once from Microsoft Graph `/me` so the agent can tell them which account is connected), are kept in the plugin's storage in your Dify installation, keyed by a hash of the Dify user ID and encrypted with a key derived from the client secret. During sign-in, the one-time authorization code is held briefly until it is redeemed. Tokens are never returned to the agent or included in tool output or error messages. A user's tokens are kept until the user signs out (Sign Out of To Do tool), the refresh token stops working, or the client secret is rotated.

## Third-Party Services

This plugin interacts with Microsoft To Do via the official Microsoft Graph API (graph.microsoft.com, or the national-cloud endpoint selected in the plugin settings) and signs in through Microsoft Entra ID. Please refer to Microsoft's privacy policy for details on how your data is handled by Microsoft services.

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: November 1, 2026
