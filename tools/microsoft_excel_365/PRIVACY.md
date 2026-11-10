# Privacy Policy

**Effective Date: September 15, 2026** (last revised November 1, 2026)

This Privacy Policy explains how we collect, use, and protect your information when you use the Microsoft Excel 365 Plugin for Dify.

## Information Collection

We do not collect or share any personal information from users, and store only the sign-in data described under Data Security. All data processed by the plugin is handled locally or through secure connections to Microsoft Excel 365 services via Microsoft Graph API, as required for functionality.

## Use of Information

The plugin only accesses your Microsoft Excel 365 data to provide the requested features, such as reading, writing, creating, and managing Excel workbooks and worksheets. This includes file management, workbook operations, worksheet data manipulation, and search functionality. No data is stored or transmitted to third parties by the plugin itself.

## Data Security

We are committed to ensuring the security of your data. All communications with Microsoft Excel 365 services use secure protocols (such as HTTPS) through Microsoft Graph API. We do not retain Excel data or workbook information beyond a request. Credentials (OAuth tokens, or the tenant ID, client ID, client secret and default drive owner of a Service Principal) are stored by your Dify workspace; with a Service Principal, the short-lived app token is kept in the plugin process's memory until it expires.

With "Each user signs in", the workspace credential holds only the app registration (tenant ID, client ID, client secret, sign-in callback URL). Each chat user's Microsoft access and refresh tokens, and the account name they signed in with (read once from Microsoft Graph `/me` so the agent can tell them which account is connected), are kept in the plugin's storage in your Dify installation, keyed by a hash of the Dify user ID and encrypted with a key derived from the client secret. During sign-in, the one-time authorization code is held briefly until it is redeemed. Tokens are never returned to the agent or included in tool output. A user's tokens are kept until the user signs out (Sign Out of Excel tool), the refresh token stops working, or the client secret is rotated.

## Third-Party Services

This plugin interacts with Microsoft Excel 365 via Microsoft Graph API. The plugin requires OAuth2 authentication and requests the following delegated scopes:

- `offline_access`: maintain access to your data after the access token expires, without asking you to sign in again.
- `User.Read`: read your basic profile, used only to verify that the connection works.
- `Files.ReadWrite`: read and write the Excel workbooks in your own OneDrive.
- `Files.ReadWrite.All`: read and write Excel workbooks that are stored outside your own OneDrive, such as in a SharePoint site you already have access to. This scope is limited to files that you can access yourself.
- `Sites.Read.All`: read access to SharePoint sites you can already reach, used when the optional `site_id` parameter targets a site drive.

These permissions are used only to carry out the operations you invoke through the plugin's tools. Please refer to Microsoft's privacy policy for details on how your data is handled by Microsoft Excel 365 services.

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: September 15, 2026
