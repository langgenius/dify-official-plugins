# Airtable Trigger Plugin for Dify

## Overview

This plugin enables Dify to receive real-time webhook notifications from Airtable when records in your bases are created, updated, or deleted. It provides a seamless integration between Airtable and your Dify workflows.

## Features

- **Real-time Notifications**: Receive instant notifications when records change in your Airtable bases
- **Event Types**:
  - Record Created: Triggered when a new record is added to a table
  - Record Updated: Triggered when an existing record is modified
  - Record Deleted: Triggered when a record is removed from a table
- **Flexible Filtering**: 
  - Filter by specific table IDs
  - Filter by field values and keywords
  - Filter by changed fields (for update events)
- **Secure**: Optional HMAC signature verification for webhook authenticity
- **Auto-refresh**: Webhooks automatically refresh to extend their 7-day lifetime

## Prerequisites

1. An Airtable account with access to a base
2. A Personal Access Token from Airtable with the following scopes:
   - `webhook:manage` - Required for creating and managing webhooks
   - `data.records:read` - Required for reading record data
   - `schema.bases:read` - Required for reading base schema

## Getting Your Airtable Personal Access Token

1. Go to [Airtable Account Settings](https://airtable.com/create/tokens)
2. Click "Create new token"
3. Give your token a name (e.g., "Dify Integration")
4. Add the following scopes:
   - `webhook:manage`
   - `data.records:read`
   - `schema.bases:read`
5. Add access to the specific bases you want to monitor
6. Click "Create token" and copy the token value

## Configuration

### Required Settings

- **Personal Access Token**: Your Airtable Personal Access Token
- **Base ID**: The ID of the Airtable base to monitor (found in the base URL: `https://airtable.com/{baseId}/...`)
- **Events**: Select which event types to monitor (created, updated, deleted)

### Optional Settings

- **MAC Secret**: A secret key for webhook signature verification (automatically generated if not provided)
- **Table IDs**: Comma-separated list of specific table IDs to monitor (leave empty to monitor all tables)

### Event-Specific Filters

Each event type supports additional filtering:

#### Record Created
- **Table ID Filter**: Only trigger for specific table
- **Field Filter**: Only trigger when a specific field contains certain keywords

#### Record Updated
- **Table ID Filter**: Only trigger for specific table
- **Changed Fields Filter**: Only trigger when specific fields are modified
- **Field Filter**: Only trigger when a specific field contains certain keywords

#### Record Deleted
- **Table ID Filter**: Only trigger for specific table

## Usage Example

1. Install the Airtable Trigger plugin in your Dify workspace
2. Create a new workflow and add an Airtable Trigger
3. Configure the trigger with your Personal Access Token and Base ID
4. Select the events you want to monitor
5. Add any optional filters to narrow down notifications
6. Save and activate your workflow

## Airtable Webhook Behavior

Important notes about how Airtable webhooks work:

- **Notification Pings**: Airtable sends lightweight notification pings that don't contain the actual record data
- **Payload Fetching**: After receiving a notification, you need to fetch the actual payload data from the Airtable API
- **Expiration**: Webhooks created with Personal Access Tokens expire after 7 days and need to be refreshed
- **Auto-refresh**: This plugin automatically refreshes webhooks to keep them active
- **Rate Limits**: Airtable API is subject to 5 requests per second per base

## Output Variables

The trigger provides the following variables to your workflow:

```json
{
  "base_id": "appXXXXXXXXXXXXXX",
  "webhook_id": "achXXXXXXXXXXXXXX",
  "timestamp": "2023-01-01T00:00:00.000Z",
  "notification": { /* full webhook notification payload */ }
}
```

## Limitations

- Personal Access Token webhooks expire after 7 days (auto-refreshed by this plugin)
- Airtable webhook notifications don't include the actual record data - you need to fetch payloads separately
- Subject to Airtable's API rate limits (5 requests/second per base)

## Troubleshooting

### Webhook Creation Fails
- Verify your Personal Access Token has the correct scopes
- Check that the Base ID is correct
- Ensure the token has access to the specified base

### No Notifications Received
- Verify the webhook was created successfully in Airtable
- Check your MAC secret is correctly configured (if used)
- Ensure the events and filters are configured correctly

### Webhook Expired
- The plugin automatically refreshes webhooks, but if manual intervention is needed, you can re-create the subscription

## References

- [Airtable Webhooks API Documentation](https://airtable.com/developers/web/api/webhooks-overview)
- [Airtable Authentication](https://airtable.com/developers/web/api/authentication)
- [Airtable Scopes](https://airtable.com/developers/web/api/scopes)

## Support

For issues or questions:
- Check the Airtable API documentation
- Review Dify plugin documentation
- Contact support with specific error messages
