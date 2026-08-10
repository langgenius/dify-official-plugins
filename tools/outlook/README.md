# Outlook

Dify's integration with Microsoft Outlook (via Microsoft Graph) for **email and calendar** — read, send and organize mail, and manage calendar events.

## Features

### Email
- **List Messages** — list messages from your Outlook inbox.
- **Get Message** — detailed info about a specific email by its ID.
- **Send Message** — send an email through Outlook.
- **Send Draft** — send a draft email (needs a draft ID from Draft Email).
- **Draft Email** — create a draft email.
- **List Draft Emails** — list your draft emails.
- **Add Attachment to Draft** — add a file attachment to a draft.
- **Prioritize Email** — set the priority level of an email.
- **Flag Message** — flag / unflag a message.

### Calendar (new in 0.3.0)
- **List Calendars** — list your calendars.
- **List Events** — list upcoming events (optionally from a specific calendar).
- **Create Event** — create a meeting/appointment (supports attendees, location and a Teams online meeting).
- **Get Event** — get a single event by ID.
- **Update Event** — update fields of an event.
- **Delete Event** — delete an event.

## Setup (OAuth2 with Azure AD)

1. Register an application in the [Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade); copy the **Client ID** and create a **Client Secret**.
2. Under **API permissions**, add these delegated Microsoft Graph permissions and grant consent:
   - `Mail.Read`, `Mail.Send`, `Mail.ReadWrite` — email
   - `Calendars.ReadWrite` — calendar
   - `offline_access` — token refresh
3. Add the redirect URI shown by Dify.
4. In Dify, configure the plugin with **Client ID**, **Client Secret** and (optional) **Tenant ID** (leave blank / `common` for personal or multi-tenant), then complete the OAuth sign-in.

> Existing installs: adding the calendar tools introduces the `Calendars.ReadWrite` scope — you will be asked to re-authorize once.

## Usage

Add the Outlook tools to an agent or workflow, fill in the inputs, and run the node. For calendar, a common flow is **List Calendars** → **Create Event** / **List Events**.

## Privacy

This plugin sends the inputs required by the selected operation to Microsoft Graph. See [PRIVACY.md](PRIVACY.md) for details.
