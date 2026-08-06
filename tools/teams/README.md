# Microsoft Teams

**Author:** langgenius
**Type:** tool

## Overview

Post messages into Microsoft Teams **channels** and **chats**, and list your teams, channels and chats — via the Microsoft Graph API with OAuth2. Ideal for broadcasting the same message into a team channel from a Dify workflow or agent.

## Tools

- **List Teams** — the teams you belong to (`GET /me/joinedTeams`).
- **List Channels** — channels in a team (`GET /teams/{team-id}/channels`).
- **Send Channel Message** — post a message to a channel (`POST /teams/{team-id}/channels/{channel-id}/messages`).
- **Send Chat Message** — post a message to a 1:1 or group chat (`POST /chats/{chat-id}/messages`).
- **List Chats** — your recent chats (`GET /me/chats`).
- **List Channel Messages** — recent messages in a channel.

Typical flow: **List Teams** → **List Channels** (grab the channel id) → **Send Channel Message**.

## Setup (Azure AD app + OAuth2)

1. In the [Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade), register an application.
2. Copy the **Application (client) ID** and, under **Certificates & secrets**, create a **client secret**.
3. Under **API permissions**, add these **delegated** Microsoft Graph permissions and grant consent:
   - `Team.ReadBasic.All`, `Channel.ReadBasic.All` — list teams/channels
   - `ChannelMessage.Send` — post channel messages
   - `Chat.ReadWrite`, `ChatMessage.Send` — list/post chats
   - `User.Read`, `offline_access`
4. Add the redirect URI shown by Dify when you connect the plugin.
5. In Dify, configure the plugin with **Client ID**, **Client Secret** and (optional) **Tenant ID** — leave Tenant ID blank / `common` for personal or multi-tenant apps — then complete the OAuth sign-in.

## Notes

- Auth uses delegated permissions, so messages are posted **as the signed-in user**.
- Access tokens are refreshed automatically via the stored refresh token (`offline_access`).

## Privacy

See [PRIVACY.md](PRIVACY.md).
