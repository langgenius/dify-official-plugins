# Microsoft Teams — Usage Guide

This plugin posts messages into Microsoft Teams **channels** and **chats** and lists your teams, channels and chats, via the Microsoft Graph API (OAuth2, delegated — actions run as the signed-in user).

## 1. Create an Azure AD application

1. Go to **[Azure Portal → App registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)** → **New registration**.
2. Copy the **Application (client) ID**.
3. **Certificates & secrets** → **New client secret** → copy the secret **value**.
4. **API permissions** → **Add a permission** → **Microsoft Graph** → **Delegated permissions**, add:
   - `Team.ReadBasic.All`, `Channel.ReadBasic.All`
   - `ChannelMessage.Send`
   - `Chat.ReadWrite`, `ChatMessage.Send`
   - `User.Read`, `offline_access`
   
   Then **Grant admin consent** (if your tenant requires it).

## 2. Connect in Dify

1. Install the plugin and open its settings.
2. Enter **Client ID**, **Client Secret**, and (optional) **Tenant ID** — leave blank / `common` for personal or multi-tenant apps.
3. Copy the **redirect URI** shown by Dify and add it to your Azure app under **Authentication → Web → Redirect URIs**.
4. Complete the **OAuth sign-in** with your Microsoft account.

## 3. Post to a channel

Typical flow:

1. **List Teams** → get the `team_id` of your team.
2. **List Channels** (with that `team_id`) → get the `channel_id`.
3. **Send Channel Message** with `team_id`, `channel_id`, and your `message` (set `content_type` to `html` or `text`).

For 1:1 or group chats, use **List Chats** to get a `chat_id`, then **Send Chat Message**.

## Tools

| Tool | Graph endpoint |
|---|---|
| List Teams | `GET /me/joinedTeams` |
| List Channels | `GET /teams/{team-id}/channels` |
| Send Channel Message | `POST /teams/{team-id}/channels/{channel-id}/messages` |
| Send Chat Message | `POST /chats/{chat-id}/messages` |
| List Chats | `GET /me/chats` |
| List Channel Messages | `GET /teams/{team-id}/channels/{channel-id}/messages` |

## Troubleshooting

- **403 / Authorization_RequestDenied** — a required delegated permission is missing or not consented. Re-check the scopes above and grant admin consent.
- **401** — token expired; re-authorize. Tokens refresh automatically via `offline_access`.
- **Channel/chat not found** — verify the `team_id` / `channel_id` / `chat_id` from the List tools.
