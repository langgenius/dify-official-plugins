# Microsoft Teams

**Author:** langgenius
**Type:** tool

## Overview

Post and reply to messages in Microsoft Teams **channels** and **chats**, start chats, create online meetings, and manage **Planner** tasks — via the Microsoft Graph API with OAuth2. Works in the global cloud and in national clouds (US Government, China/21Vianet).

## Tools

- **List Teams** — the teams you belong to (`GET /me/joinedTeams`).
- **List Channels** — channels in a team (`GET /teams/{team-id}/channels`).
- **Send Channel Message** — post a message to a channel (`POST /teams/{team-id}/channels/{channel-id}/messages`).
- **Send Chat Message** — post a message to a 1:1 or group chat (`POST /chats/{chat-id}/messages`).
- **List Chats** — your chats with their participants (name, user ID, email), a display name (the topic, or the other participants) and web link. Filter by an exact participant name and/or email and by chat type (one-on-one, group, meeting); reads several pages and returns `pagination.next_link` to continue (`GET /me/chats?$expand=members`).
- **List Chat Messages** (new in 0.2.0) — the messages of a chat, newest first, by created or last-modified time with an optional time window; system events are left out unless asked for (`GET /chats/{chat-id}/messages`).
- **List Channel Messages** — recent messages in a channel.
- **List Group Calendar Events** — events from a team's Microsoft 365 group calendar, optionally within a start/end date range (`GET /groups/{team-id}/calendarView`); returns subject, start/end, organizer, attendees and Teams meeting info.

### Channel threads (new in 0.2.0)
- **Reply to Channel Message** — reply in a message's thread (`POST …/messages/{message-id}/replies`).
- **List Channel Message Replies** — the replies in a thread.

### Chats (new in 0.2.0)
- **Create Chat** — start a one-on-one or group chat with users given by UPN or user ID; the signed-in user is added automatically, and an existing one-on-one chat is returned instead of a duplicate.
- **List Chat Members** — members of a chat (names, emails, user IDs).

### Online meetings (new in 0.2.0)
- **Create Online Meeting** — a standalone Teams meeting with its join link (`POST /me/onlineMeetings`). Times are ISO 8601; a value without a UTC offset is taken as UTC.
- **Get Online Meeting** / **Delete Online Meeting** — by meeting ID.

### Planner (new in 0.2.0)
- **List Planner Plans** — plans of a team.
- **List Planner Buckets** — buckets (columns) of a plan.
- **List Planner Tasks** — tasks of a plan, optionally without completed ones.
- **Create Planner Task** — with bucket, due date and assignees (user IDs, or `me`).
- **Update Planner Task** — title, bucket, progress (`percent_complete`: 0 / 50 / 100) or due date.
- **Delete Planner Task**.

Typical flows: **List Teams** → **List Channels** → **Send Channel Message** / **Reply to Channel Message**; **List Teams** → **List Planner Plans** → **Create Planner Task**.

## Setup (Azure AD app + OAuth2)

1. In the [Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade), register an application.
2. Copy the **Application (client) ID** and, under **Certificates & secrets**, create a **client secret**.
3. Under **API permissions**, add these **delegated** Microsoft Graph permissions and grant consent:
   - `Team.ReadBasic.All`, `Channel.ReadBasic.All` — list teams/channels
   - `ChannelMessage.Send` — post channel messages
   - `Chat.ReadWrite`, `ChatMessage.Send` — list/post chats
   - `Group.Read.All` — read a team's group calendar (List Group Calendar Events; admin consent required)
   - `ChannelMessage.Read.All` — read channel messages and replies (admin consent required)
   - `OnlineMeetings.ReadWrite` — create, get and delete online meetings
   - `Tasks.ReadWrite` — Planner plans, buckets and tasks
   - `User.Read`, `offline_access`
4. Add the redirect URI shown by Dify when you connect the plugin.
5. In Dify, configure the plugin with **Client ID**, **Client Secret**, (optional) **Tenant ID** — leave it blank / `common` for personal or multi-tenant apps — and **Microsoft Cloud** (Global unless your tenant is in a national cloud), then complete the OAuth sign-in.

> Upgrading from 0.1.x: 0.2.0 asks for three more delegated permissions (`ChannelMessage.Read.All`, `OnlineMeetings.ReadWrite`, `Tasks.ReadWrite`). Add them to the app registration, grant consent, and re-authorize once. Existing authorizations keep working for the 0.1.x tools in the meantime.

## Notes

- Auth uses delegated permissions, so messages are posted **as the signed-in user**.
- Access tokens are refreshed automatically via the stored refresh token (`offline_access`).

## Privacy

See [PRIVACY.md](PRIVACY.md).
