## Privacy Policy

This privacy policy outlines how the Dify Jira Plugin handles your information when you use it to interact with Jira.

### Data Collection

The Dify Jira Plugin uses the following information to function:

1.  **Credentials**, depending on the mode you choose:
    -   **API token**: your Jira URL and API token (or personal access token).
    -   **OAuth**: the Client ID and Client Secret of your Atlassian OAuth app. After authorization, also the access and refresh tokens, the ID and URL of the Jira site, and the authorizing account's email.
    -   **Each user signs in**: the Client ID and Client Secret of your Atlassian OAuth app and the sign-in callback URL. For every user who signs in, also that user's access and refresh tokens, the ID and URL of their Jira site, and their account email.
2.  **User Inputs:** Data you provide when using the plugin's tools, such as JQL queries, issue keys, summaries, descriptions, comments, attachments, account IDs, and notification text. These are collected to perform the requested actions.

### Data Processing

-   **Credentials and tokens:** Used only to authenticate requests to Jira (your Jira URL, or `api.atlassian.com` for OAuth) and to Atlassian's sign-in service (`auth.atlassian.com`). They are never included in tool output.
-   **User Inputs:** Used to build the Jira API requests that perform the actions you ask for.

### Data Storage

-   **Workspace credentials:** API tokens, OAuth app details and OAuth tokens are stored by Dify's credential management.
-   **Each user signs in:** Each user's tokens, Jira site and account email are kept in the plugin's own storage in your Dify instance. They are encrypted with a key derived from the Client Secret. While a sign-in is in progress, the plugin also stores a random state value and, briefly, the one-time authorization code.
-   **Removing stored sign-ins:**
    -   One user's sign-in is removed when that user asks the agent to sign out (`jira_sign_out`).
    -   Changing the Client Secret makes every stored sign-in unreadable.
    -   Users can also revoke the app in their Atlassian account settings (Connected apps).

### Third-party Services

This plugin talks only to **Atlassian** (Jira, `api.atlassian.com`, `auth.atlassian.com`). Your use of Jira is subject to Atlassian's privacy policy and terms of service. No data is shared with any other third party.

### Data Retention

Apart from the per-user sign-ins described above, the plugin does not keep your data. Issues, comments and attachments live in Jira and follow its retention policies. Logs written by Dify while the plugin runs follow Dify's platform policies.

### User Rights

-   **Data in Jira:** governed by your Jira settings and Atlassian's policies.
-   **Data held by Dify:** see Dify's privacy policy. Each user can sign out at any time, and Atlassian accounts can revoke the app's access.

### Contact Information

If you have any questions or concerns about the privacy practices of this plugin, please contact the plugin author.

Last updated: November 1, 2026
