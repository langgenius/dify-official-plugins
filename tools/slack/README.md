# Slack

**Author:** langgenius
**Type:** tool

## Overview

Slack is a cloud-based team communication platform. This plugin lets Dify apps and agents interact with a Slack workspace through the **Slack Web API** using a Bot User OAuth Token, covering messages, channels, users, reactions, and files. It also keeps the classic **Incoming Webhook** tool for simple one-way message posting.

## Tools

### Messages
- **Send Message** – post a message to a channel, group, or DM (`chat.postMessage`), with optional threaded reply.
- **Update Message** – edit a message the bot posted (`chat.update`).
- **Delete Message** – delete a message (`chat.delete`).
- **Get Message Permalink** – get a permalink URL for a message (`chat.getPermalink`).
- **Schedule Message** – schedule a message for future delivery (`chat.scheduleMessage`).
- **Incoming Webhook** – post a message via an Incoming Webhook URL (no bot token needed).

### Channels
- **List Channels** – list conversations (`conversations.list`).
- **Get Channel Info** – channel metadata (`conversations.info`).
- **Create Channel** – create a public or private channel (`conversations.create`).
- **Get Channel History** – fetch recent messages (`conversations.history`).
- **Get Thread Replies** – fetch replies in a thread (`conversations.replies`).
- **Invite Users to Channel** – add users to a channel (`conversations.invite`).
- **Archive Channel** – archive a channel (`conversations.archive`).
- **Set Channel Topic** – set a channel's topic (`conversations.setTopic`).

### Reactions
- **Add Reaction** – add an emoji reaction (`reactions.add`).
- **Remove Reaction** – remove an emoji reaction (`reactions.remove`).

### Users
- **List Users** – list workspace members (`users.list`).
- **Get User Info** – get a user's profile (`users.info`).
- **Look Up User by Email** – find a user by email (`users.lookupByEmail`).

### Files
- **Upload File** – upload a file and optionally share it to a channel (`files.getUploadURLExternal` + `files.completeUploadExternal`).

## Configuration

### Option A — Bot User OAuth Token (recommended, unlocks all tools)

Go to the [Slack API platform](https://api.slack.com/apps) and click **Create New App**. Slack offers two ways to create the app — either works:

#### Fastest — "From a manifest" (pre-fills all scopes)

1. Choose **From a manifest**, select your workspace, and paste the manifest below.
2. Click **Next → Create**.
3. On the app page, click **Install to Workspace** and authorize.
4. Open **OAuth & Permissions** and copy the **Bot User OAuth Token** (starts with `xoxb-`).

```yaml
display_information:
  name: Dify Slack
features:
  bot_user:
    display_name: Dify Slack
    always_online: false
oauth_config:
  scopes:
    bot:
      - chat:write
      - channels:read
      - groups:read
      - channels:manage
      - groups:write
      - channels:history
      - groups:history
      - reactions:write
      - users:read
      - users:read.email
      - files:write
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
```

> Paste it exactly as-is. The `features.bot_user` block is required — Slack rejects a manifest that requests `bot` scopes without declaring a bot user. Also note Slack's manifest editor does not accept inline `#` comments, so the block above is comment-free; each scope's purpose is listed in the table under the "Blank app" section below.

#### Manual — "Blank app" (the new name for "From scratch")

1. Choose **Blank app**, name it, and pick your workspace.
2. Go to **OAuth & Permissions → Scopes → Bot Token Scopes** and add the scopes for the tools you need:

   | Scope | Enables |
   |---|---|
   | `chat:write` | send / update / delete / schedule messages, get permalink |
   | `channels:read`, `groups:read` | list & read channels |
   | `channels:manage`, `groups:write` | create / archive / set-topic / invite |
   | `channels:history`, `groups:history` | read channel history & thread replies |
   | `reactions:write` | add / remove reactions |
   | `users:read`, `users:read.email` | list / get / look-up users |
   | `files:write` | upload files |

3. Click **Install to Workspace** and authorize.
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`).

#### Then, in Dify

5. Install the Slack plugin and paste the token into the **Access Token** field. (A user token starting with `xoxp-` is also accepted, in which case actions run as the authorizing user.)
6. Invite the bot to any channel it needs to act in (`/invite @your-bot`).

> **Note:** You must click **Install to Workspace** *after* adding scopes for the `xoxb-` token to appear. Changing scopes later requires re-installing the app.

### Option B — Incoming Webhook (Incoming Webhook tool only)

1. In your Slack app settings, enable **Incoming Webhooks** and **Add New Webhook to Workspace**.
2. Copy the webhook URL (starts with `https://hooks.slack.com/`).
3. Provide it as the `webhook_url` parameter of the **Incoming Webhook** tool.

## Notes

- Bot tokens cannot use `search.messages` (that requires a user token), so message search is not included.
- The bot must be a member of a channel to read its history or post to it (unless the channel is public and your scopes allow it).

## Privacy

See [PRIVACY.md](PRIVACY.md).
