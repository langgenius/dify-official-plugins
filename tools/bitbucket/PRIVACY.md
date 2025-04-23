## Privacy Policy

This Dify plugin interacts with the BitBucket API to perform actions on your behalf within your BitBucket account.

**Data Access:**

To function, this plugin requires access to your BitBucket account data via API credentials. The specific data accessed depends on the actions you invoke through the plugin, which may include:

*   Workspace information (listing workspaces)
*   Project information (listing, creating, viewing details, managing permissions)
*   Repository information (listing, creating, updating, managing permissions, labels, branching models, forking)
*   Code Insights data (creating, deleting reports, adding annotations)
*   User and group information (listing users/groups, managing permissions)
*   Code data (listing branches, creating/deleting branches, managing pull requests, comments, tags, diffs, commits, file content)
*   Branch permissions
*   Pull request details (activities, changes, commits, comments, reviewers, merging, declining, reopening)
*   Conditions and reviewers
*   BitBucket Cloud specific data (workspaces, permissions, projects, repositories, deployment environments, variables, hooks, members)
*   Pipeline information (listing, triggering, stopping, viewing steps and logs)
*   Issue tracking data (listing, creating, updating, deleting issues)

**Data Usage:**

The data accessed via the BitBucket API is used solely to perform the requested actions initiated by you through the Dify interface. For example:

*   Listing your repositories requires accessing repository data.
*   Creating a pull request requires accessing repository and branch data, and potentially user data for reviewers.
*   Adding a comment requires accessing pull request data.

**Data Storage:**

This plugin **does not store** your BitBucket API credentials or any sensitive data retrieved from the BitBucket API persistently. Authentication tokens or credentials might be held temporarily in memory during the execution of a request but are discarded afterward. The plugin operates as a stateless intermediary between Dify and the BitBucket API.

**Data Sharing:**

We do not share your BitBucket data accessed through this plugin with any third parties. All interactions occur directly between Dify, this plugin, and the official BitBucket API.

**User Control:**

You maintain full control over your BitBucket account and the data within it. You can revoke the plugin's access or uninstall it at any time through the Dify platform. The actions performed by the plugin are based on the permissions associated with the BitBucket credentials you provide.

**Changes to this Policy:**

We may update this privacy policy from time to time. We will notify you of any significant changes.

**Contact:**

For privacy-related inquiries regarding this plugin, please contact: support@dify.ai
