# Privacy Policy

**Effective Date: November 2, 2026**

This Privacy Policy explains how we collect, use, and protect your information when you use the Google Calendar Plugin for Dify.

## Information Collection

Apart from the per-user sign-ins described below, we do not collect, store, or share any personal information from users. All data processed by the plugin is handled locally or through secure connections to Google services, as required for functionality.

### "Each user signs in" mode

When the plugin is set to "Each user signs in", it keeps a small amount of data in its own storage in your Dify instance:
- **Per user**: that user's Google access and refresh tokens and the email of the Google account they signed in with.
- **While a sign-in is in progress**: a random state value, a PKCE verifier and, briefly, the one-time authorization code. These are deleted once the sign-in finishes or expires.

How this data is protected and removed:
- **Encrypted**: it is encrypted with a key derived from the OAuth client secret.
- **Never shown**: it is never included in tool output.
- **Removing one user's sign-in**: the user asks the agent to sign out (`google_calendar_sign_out`).
- **Removing everyone's sign-ins**: change the client secret; the stored sign-ins can no longer be read.
- **Revoking from Google**: users can also revoke access in their Google account (Security › Third-party access).

## Use of Information

The plugin only accesses your Google Calendar data to provide the requested features, such as viewing, creating, or managing calendar events. No data is stored or transmitted to third parties by the plugin itself.

## Data Security

We are committed to ensuring the security of your data. All communications with Google services use secure protocols (such as HTTPS). We do not retain calendar data beyond the duration of your session. Credentials are kept only as described above: OAuth credentials by Dify's credential management, and per-user sign-ins, encrypted, in the plugin's storage.

## Third-Party Services

This plugin interacts with Google Calendar via official APIs. Please refer to Google's privacy policy for details on how your data is handled by Google services.

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: November 2, 2026
