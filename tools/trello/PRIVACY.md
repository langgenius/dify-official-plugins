## Privacy Policy

This privacy policy outlines how the Dify Trello Plugin handles your information when you use it to interact with Trello.

### Data Collection

The plugin uses the following information to function:

1.  **Credentials**, depending on the mode you choose:
    -   **API key + token**: your Trello API key and token.
    -   **Each user signs in**: your Trello API key and secret, and the sign-in callback URL. For every user who signs in, also that user's Trello token, member ID, and Trello name and username.
2.  **User Inputs:** Data you provide when using the tools, such as search text, board, list and card IDs, card names and descriptions, comments, checklist items, labels, email addresses to invite, and attachments.

### Data Processing

-   **Credentials and tokens:** Used only to authenticate requests to the Trello API (`api.trello.com`). They are sent in the Authorization header, never in URLs, and are never included in tool output.
-   **User Inputs:** Used to build the Trello API requests that perform the actions you ask for.

### Data Storage

-   **Workspace credentials:** The API key, token and secret are stored by Dify's credential management.
-   **Each user signs in:**
    -   Each user's token, member ID and name are kept in the plugin's own storage in your Dify instance, encrypted with a key derived from the API secret.
    -   While a sign-in is in progress, the plugin also stores a random state value, a one-time public key, and the token sealed with that key; these are deleted once the sign-in finishes or expires.
-   **Removing stored sign-ins:**
    -   One user's sign-in is removed when that user asks the agent to sign out (`trello_sign_out`).
    -   Changing the API secret makes every stored sign-in unreadable.
    -   Users can also revoke access in Trello (Settings › Applications).

### Third-party Services

This plugin talks only to **Trello** (Atlassian). Your use of Trello is subject to Atlassian's privacy policy and terms of service. No data is shared with any other third party.

### Data Retention

Apart from the per-user sign-ins described above, the plugin does not keep your data. Boards, cards and attachments live in Trello and follow its retention policies. Logs written by Dify while the plugin runs follow Dify's platform policies.

### Contact Information

If you have any questions or concerns about the privacy practices of this plugin, please contact the plugin author.

Last updated: November 2, 2026
