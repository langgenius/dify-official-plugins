# Airtable Trigger

A Dify plugin that enables real-time webhook notifications from Airtable when records are created, updated, or deleted in your bases.

## Features

- Real-time notifications for record changes
- Support for create, update, and delete events
- Flexible filtering by table, fields, and keywords
- Secure HMAC signature verification
- Auto-refresh webhooks (7-day expiration handling)

## Quick Start

1. Get your Airtable Personal Access Token with required scopes:
   - `webhook:manage`
   - `data.records:read`
   - `schema.bases:read`

2. Find your Base ID from your Airtable base URL

3. Configure the plugin with your token and base ID

4. Select which events to monitor and add any filters

For detailed documentation, see [README.md](./README.md)
