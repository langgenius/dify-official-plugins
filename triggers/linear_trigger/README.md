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

### 1. Install Dependencies

```bash
cd linear_from_github
uv pip install -r requirements.txt
```

### 2. Authentication

#### Option A: API Key
1. Go to [Linear Settings > API](https://linear.app/settings/api)
2. Create a Personal API Key
3. Copy the key for plugin configuration

#### Option B: OAuth 2.0 (Recommended for teams)
1. Go to [Linear Settings > API Applications](https://linear.app/settings/api/applications)
2. Create a new OAuth Application
3. Configure Client ID and Client Secret in Dify

### 3. Set Up Webhook in Linear

1. Go to Linear Workspace Settings > Webhooks
2. Create new webhook pointing to your Dify endpoint
3. Select resource types to monitor
4. (Optional) Add webhook secret for verification

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

## Usage Example

```yaml
# High-priority issue automation
trigger:
  type: linear_trigger.issue_created
  parameters:
    priority_filter: "1,2"  # Urgent and High only
    team_filter: "team-id-123"

workflow:
  - send_slack_alert:
      channel: "#critical-issues"
      message: "🚨 New urgent issue: {{trigger.data.title}}"
```

## Package Plugin

```bash
# From parent directory
/Applications/Development/difyplugin/dify-plugin-darwin-arm64-new plugin package linear_from_github -o linear_trigger.difypkg
```

## Changelog

### Version 0.3.0 (2025-10-16)
- ✅ **Added 29 new events** (44 total):
  - Attachment events (3)
  - IssueLabel events (3)
  - Reaction events (3)
  - ProjectUpdate events (3)
  - Initiative events (3)
  - InitiativeUpdate events (3)
  - Customer events (3)
  - CustomerNeed events (3)
  - User events (2)
  - IssueRelation events (3)
- ✅ Complete Linear webhook coverage
- ✅ All events tested and validated

### Version 0.2.0 (2025-10-16)
- ✅ Added Issue, Comment, Project, Cycle, Document events (15 total)
- ✅ Comprehensive test coverage
- ✅ Enhanced filtering capabilities

### Version 0.1.4
- ✅ Fixed OAuth implementation
- ✅ Fixed OAuth token exchange format
- ✅ Fixed credential key naming

## Testing

```bash
# Run all tests
uv run python -m pytest tests/ -v

# Run specific event tests
uv run python -m pytest tests/events/issue/ -v
uv run python -m pytest tests/events/project/ -v
```

## Support

- GitHub: [dify-plugins](https://github.com/langgenius/dify-plugins)
- Dify Community: [discussions](https://github.com/langgenius/dify/discussions)
- Linear API: [developers.linear.app](https://developers.linear.app)

