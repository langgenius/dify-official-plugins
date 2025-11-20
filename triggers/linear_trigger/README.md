# Linear Trigger Plugin

A comprehensive Dify plugin providing 44 Linear webhook event triggers for your workflows. Monitor and respond to all Linear events including issues, comments, projects, cycles, documents, and more.

## Features

- **44 Event Types**: Complete coverage of all Linear webhook events
- **Dual Authentication**: Both API Key and OAuth 2.0 support
- **Webhook Signature Verification**: Securely validates Linear webhook requests
- **Flexible Filtering**: Filter events by priority, state, name, team, and more
- **Rich Event Data**: Extracts detailed information from Linear webhook payloads

## Version

**Current Version**: 0.3.0

## Available Events (44 Total)

### Issue Events (3)
- `issue_created`: New issue created
- `issue_updated`: Issue updated
- `issue_removed`: Issue deleted or archived

### Comment Events (3)
- `comment_created`: New comment added
- `comment_updated`: Comment edited
- `comment_removed`: Comment deleted

### Project Events (3)
- `project_created`: New project created
- `project_updated`: Project updated
- `project_removed`: Project deleted or archived

### Cycle Events (3)
- `cycle_created`: New cycle created
- `cycle_updated`: Cycle updated
- `cycle_removed`: Cycle deleted or archived

### Document Events (3)
- `document_created`: New document created
- `document_updated`: Document updated
- `document_removed`: Document deleted or archived

### Attachment Events (3)
- `attachment_created`: New attachment added
- `attachment_updated`: Attachment updated
- `attachment_removed`: Attachment deleted

### IssueLabel Events (3)
- `issue_label_created`: New label created
- `issue_label_updated`: Label updated
- `issue_label_removed`: Label deleted

### Reaction Events (3)
- `reaction_created`: New reaction added
- `reaction_updated`: Reaction updated
- `reaction_removed`: Reaction removed

### ProjectUpdate Events (3)
- `project_update_created`: New project update posted
- `project_update_updated`: Project update edited
- `project_update_removed`: Project update deleted

### Initiative Events (3)
- `initiative_created`: New initiative created
- `initiative_updated`: Initiative updated
- `initiative_removed`: Initiative deleted

### InitiativeUpdate Events (3)
- `initiative_update_created`: New initiative update posted
- `initiative_update_updated`: Initiative update edited
- `initiative_update_removed`: Initiative update deleted

### Customer Events (3)
- `customer_created`: New customer created
- `customer_updated`: Customer updated
- `customer_removed`: Customer deleted

### CustomerNeed Events (3)
- `customer_need_created`: New customer need created
- `customer_need_updated`: Customer need updated
- `customer_need_removed`: Customer need deleted

### User Events (2)
- `user_created`: New user added
- `user_updated`: User updated

### IssueRelation Events (3)
- `issue_relation_created`: New issue relation created
- `issue_relation_updated`: Issue relation updated
- `issue_relation_removed`: Issue relation removed

## Quick Start
### 1. Authentication & Subscription Options

This plugin supports **three modes** for Linear webhook subscription and authentication. Choose the option that best fits your use case:

#### Option 1: OAuth 2.0 (Recommended)

**Default OAuth Client (Dify Cloud)**
- On Dify Cloud, Linear is pre-configured with a default OAuth client for one-click authorization.
- Select **Create with OAuth > Default** and authorize Dify with Linear instantly.

**Custom OAuth Client (Self-hosted)**
- In self-hosted environments, you need to create your own OAuth application.
- Select **Create with OAuth > Custom**.
- Go to [Linear Settings > API Applications](https://linear.app/settings/api/applications) and create a new OAuth Application.
- Use the callback URL provided by Dify when creating the OAuth application in Linear.
- Back in Dify, enter the Client ID and Client Secret from your Linear OAuth application, then click **Save and Authorize**.
- Once saved, the same client credentials can be reused for future subscriptions.
- Specify the subscription name, select the events you want to subscribe to, and configure any other required settings.
- We recommend selecting all available events.
- Click **Create**.

The Callback URL displayed on the subscription configuration page is used internally by Dify to create the webhook in Linear on your behalf. You don't need to take any action with this URL.

#### Option 2: API Key Authentication

- Select **Create with API Key**.
- Go to [Linear Settings > API](https://linear.app/settings/api) and create a Personal API Key.
- Enter the API Key in Dify, then click **Verify**.
- Specify the subscription name, select the events you want to subscribe to, and configure any other required settings.
- We recommend selecting all available events.
- Click **Create**.

#### Option 3: Manual Webhook Setup

- Select **Paste URL** to create a new subscription.
- Specify the subscription name and use the provided callback URL to manually create a webhook in Linear.
- Go to Linear Workspace Settings > Webhooks and create a new webhook pointing to the Dify callback URL.
- (Optional) Add a webhook secret in Linear for request signature verification.
- (Optional) Test the created webhook:
  - Linear automatically tests new webhooks by sending a ping request to Dify upon creation.
  - You can also trigger a subscribed event so Linear sends an HTTP request to the callback URL.
  - Check the **Request Logs** section on the Manual Setup page. If the webhook works properly, you'll see the received request and Dify's response.
- Click **Create**.

**Note:**  
- For best security and team management, OAuth 2.0 is recommended.
- Webhook Secret (optional in Linear) enables request signature validation for extra security.

Please refer to Dify’s plugin configuration page or Linear documentation for step-by-step guidance if you are unsure which option matches your needs.

## Event Parameters

Each event supports specific filter parameters to reduce noise:

### Common Filters

- **title_contains/name_contains/body_contains**: Keyword filters (comma-separated)
- **priority_filter**: Filter by priority level (0-4)
- **state_filter**: Filter by workflow state
- **team_filter**: Filter by team ID
- **email_contains**: Filter by email pattern
- **emoji_filter**: Filter by specific emoji
- **issue_only**: Only trigger for issue-related items
- **project_only**: Only trigger for project-related items
- **status_changed**: Only trigger on status changes



## Support

Reference: [Linear Webhooks documentation](https://linear.app/developers/webhooks)

