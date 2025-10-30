# Notion Trigger Plugin

This plugin enables Dify to react to real-time Notion activity—including updates to pages, databases, data sources, and comments—by subscribing to Notion webhooks. When events occur in your Notion workspace, Notion securely POSTs event payloads to your configured Dify endpoint. The plugin maps event data into Dify trigger variables so you can build automations or process changes instantly, without polling.

Learn more about Notion webhooks and supported event types in the [Notion API documentation](https://developers.notion.com/reference/webhooks).


## Configure the Webhook Subscription

1. In Notion, open the integration settings → Webhooks → Create a subscription.
2. Paste the trigger endpoint provided by Dify as the webhook URL.
3. Select the event types you want Notion to emit. (You can change this list later.)
4. Submit the form. Notion immediately POSTs a JSON payload containing only `{"verification_token": "..."}`.
5. In Dify, create a new trigger connection for this plugin and paste the `verification_token` value into the Verification Token field. Optionally select the same event types in the Event Filters checkbox list to forward only a subset to the workflow.
6. Return to Notion and click Verify. Once verification succeeds, Notion will start delivering full webhook events to Dify.


### Workspace Filtering

Every event definition includes an optional `workspace_filter` parameter. Provide a comma-separated list of workspace IDs to restrict the trigger to those workspaces only. Leave the field empty to accept events from any workspace tied to the subscription.

## Supported Events

### Page
- `page.created`
- `page.deleted`
- `page.undeleted`
- `page.content_updated`
- `page.moved`
- `page.properties_updated`
- `page.locked`
- `page.unlocked`

### Database
- `database.created`
- `database.content_updated`
- `database.deleted`
- `database.undeleted`
- `database.moved`
- `database.schema_updated`

### Data Source (API version 2025-09-03)
- `data_source.created`
- `data_source.deleted`
- `data_source.undeleted`
- `data_source.moved`
- `data_source.content_updated`
- `data_source.schema_updated`

### Comment
- `comment.created`
- `comment.updated`
- `comment.deleted`
