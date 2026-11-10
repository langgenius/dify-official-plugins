## Privacy Policy

This privacy policy explains how the Dify Google Drive tool plugin handles your information.

### Data Collection

The plugin uses the following information to work:

1. **Credentials**:
   - **OAuth**: the OAuth client ID and secret of your Google Cloud project. After authorization, also the access and refresh tokens of the authorizing Google account.
   - **Each user signs in**: the OAuth client ID and secret and the sign-in callback URL. For every user who signs in, also that user's Google access and refresh tokens and the email of the account they signed in with.
2. **User inputs**: data you provide when using the tools, such as search text, file and folder IDs, file names, uploaded files and text, and email addresses or domains to share with.

### Data Processing

- **Credentials and tokens**: used only to authenticate requests to Google (the Google Drive API and Google's sign-in service). They are never included in tool output.
- **File contents**: files read, downloaded or uploaded are passed between Google Drive and your Dify workflow or agent. The plugin itself does not keep them.

### Data Storage

- **OAuth credentials** are stored by Dify's credential management.
- **Each user signs in**:
  - Per user: that user's tokens and account email, kept in the plugin's own storage in your Dify instance and encrypted with a key derived from the OAuth client secret.
  - While a sign-in is in progress: a random state value, a PKCE verifier and, briefly, the one-time authorization code. These are deleted once the sign-in finishes or expires.
- **Removing stored sign-ins**:
  - One user's sign-in is removed when that user asks the agent to sign out (`google_drive_sign_out`).
  - Changing the client secret makes every stored sign-in unreadable.
  - Users can also revoke access in their Google Account (Security › Third-party access).

### Third-party Services

This plugin talks only to **Google** (Google Drive API and Google sign-in). Your use of Google Drive is subject to Google's privacy policy and terms of service. No data is shared with any other third party.

### Data Retention

Apart from the per-user sign-ins described above, the plugin does not keep your data. Files live in Google Drive and follow its retention policies. Logs written by Dify while the plugin runs follow Dify's platform policies.

### Contact Information

If you have any questions or concerns about the privacy practices of this plugin, please contact the plugin author.

Last updated: November 2, 2026
