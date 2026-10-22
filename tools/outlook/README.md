# Outlook

Dify's integration with Microsoft Outlook (via Microsoft Graph) for **email and calendar** — read, send and organize mail, and manage calendar events.

## Features

### Email
- **List Messages** — list messages from your Outlook inbox.
- **Get Message** — detailed info about a specific email by its ID (including attachment ids).
- **Download Attachment** — download an email attachment as a file (from a `message_id` + `attachment_id`); Dify serves it over a public HTTPS URL.
- **Send Message** — send an email through Outlook, with optional file attachments.
- **Send Draft** — send a draft email (needs a draft ID from Draft Email).
- **Draft Email** — create a draft email.
- **List Draft Emails** — list your draft emails.
- **Add Attachment to Draft** — add a file attachment to a draft.
- **Prioritize Email** — set the priority level of an email.
- **Flag Message** — flag / unflag a message.

### Calendar (new in 0.3.0)
- **List Calendars** — list your calendars.
- **List Events** — list upcoming events (optionally from a specific calendar).
- **Search Events** — find events by keyword and/or a date range (uses calendarView with pagination).
- **List Calendar Groups** (new in 0.7.0) — calendar groups such as *My Calendars* and *People's calendars*; calendars other people shared with you are usually in the latter.
- **Calendar groups and shared calendars** (new in 0.7.0) — List Calendars, List Events and Search Events take an optional **Calendar Group ID**: they cover every calendar in the group and tag each event with its calendar and owner. Calendars shared with you need the `Calendars.Read.Shared` permission.
- **Get Schedule** (new in 0.7.0) — free/busy of people for a time window (Graph `getSchedule`), by email and/or a calendar group (its calendars' owners). Works for anyone in the organisation without calendar sharing; subjects only where you may see them.
- **Create Event** — create a meeting/appointment (supports attendees, location and a Teams online meeting).
- **Get Event** — get a single event by ID.
- **Update Event** — update fields of an event.
- **Delete Event** — delete an event.

## Setup

Two ways to authorize: **OAuth** (a user signs in; tools act on that user's mailbox) or **Service Principal** (app-only; tools act on a named mailbox).

### OAuth2 with Azure AD

1. Register an application in the [Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade); copy the **Client ID** and create a **Client Secret**.
2. Under **API permissions**, add these delegated Microsoft Graph permissions and grant consent:
   - `Mail.Read`, `Mail.Send`, `Mail.ReadWrite` — email
   - `Calendars.ReadWrite` — calendar
   - `Calendars.Read.Shared` — calendars other people shared with you (new in 0.7.0)
   - `offline_access` — token refresh
3. Add the redirect URI shown by Dify.
4. In Dify, configure the plugin with **Client ID**, **Client Secret** and (optional) **Tenant ID** (leave blank / `common` for personal or multi-tenant), then complete the OAuth sign-in.

> Existing installs: adding the calendar tools introduces the `Calendars.ReadWrite` scope — you will be asked to re-authorize once.
> Upgrading to 0.7.0 adds the `Calendars.Read.Shared` scope: add it to the app registration and re-authorize once.

### Service Principal (app-only, new in 0.7.0)
Use this when a workflow should run as the organisation rather than as a person: no user signs in, nothing breaks when someone leaves, and the audit log shows the app.

1. In the app registration, add Microsoft Graph **Application** permissions (not Delegated): `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, then click **Grant admin consent**.
2. Recommended: limit the app to the mailboxes it needs with an Exchange Online [RBAC for Applications](https://learn.microsoft.com/exchange/permissions-exo/application-rbac) assignment; otherwise application permissions reach every mailbox in the tenant.
3. In Dify, add an authorization of the **API Key** type and fill in **Tenant ID** (your directory ID, not `common`), **Client ID**, **Client Secret** and **Default Mailbox** (e.g. `support@contoso.com`). Dify signs in and reads that inbox to check the permissions.
4. Each tool has an optional **Mailbox** setting (set in the node, never chosen by the LLM) to act on a different mailbox with the same credential.

### National clouds (new in 0.7.0)
Both OAuth and Service Principal have a **Microsoft Cloud** setting: Global, US Government, US Government DoD, or China (21Vianet). It switches the sign-in host and the Microsoft Graph host together. Existing authorizations keep using the global cloud.

## Usage

Add the Outlook tools to an agent or workflow, fill in the inputs, and run the node. For calendar, a common flow is **List Calendars** → **Create Event** / **List Events**.

To look at the calendars of people who shared theirs with you (for example an assistant and the executives): **List Calendar Groups** → take the id of *People's calendars* → **Search Events** with that Calendar Group ID and a date range, or **Get Schedule** with it for free/busy.

## Privacy

This plugin sends the inputs required by the selected operation to Microsoft Graph. See [PRIVACY.md](PRIVACY.md) for details.
