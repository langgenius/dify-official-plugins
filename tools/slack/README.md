# Slack Plugin for Dify

**Languages:** English | [简体中文](README_zh.md) | [日本語](README_ja.md) | [한국어](README_ko.md)

**Author:** an · **Version:** 0.0.1 · **Type:** tool plugin

Automate Slack from Dify agents and workflows via the Slack Web API. Built for
feature parity with the **n8n Slack node** — 41 operations across 7 resources.

---

## Setup

1. Create a Slack app at https://api.slack.com/apps.
2. Under **OAuth & Permissions → Bot Token Scopes**, add the scopes you need
   (see each function's **Scope** below). A good starting set:
   `chat:write`, `channels:read`, `channels:manage`, `channels:history`,
   `channels:join`, `groups:read`, `files:read`, `files:write`,
   `reactions:read`, `reactions:write`, `users:read`, `users.profile:read`,
   `usergroups:read`, `usergroups:write`.
3. Install the app to your workspace and copy the **Bot User OAuth Token**
   (`xoxb-…`).
4. *(Optional)* For **Search**, **Star**, and **Update User Profile**, add
   **User Token Scopes** (`search:read`, `stars:read`, `stars:write`,
   `users.profile:write`) and copy the **User OAuth Token** (`xoxp-…`).
5. In Dify, open the Slack plugin and set the credentials:
   - **Slack Bot Token** — the `xoxb-…` token (required)
   - **Slack User Token** — the `xoxp-…` token (optional)

---

## Conventions

- **Token** — which credential a function uses:
  - **Bot** — the `Slack Bot Token` (`xoxb-…`).
  - **User ⚠️** — the optional `Slack User Token` (`xoxp-…`). Slack rejects these
    operations with a bot token; the function returns a clear error if no user
    token is set.
- **Scope** — the OAuth scope(s) the token must have. For channel operations the
  exact scope depends on the channel type; the common one is shown with
  alternates in parentheses.
- **Returns** — every function yields a **JSON message** (the raw Slack response)
  plus a short **text summary**. On failure it yields the error body and a
  `Slack error: <reason>` text message.
- **`channel`** accepts a channel ID such as `C012AB3CD` (recommended); some
  methods also accept `#channel-name`, and a user ID (`U012AB3CD`) targets a DM.
- **`ts` / `timestamp`** is a Slack message timestamp, e.g. `1716999999.000200`.
- JSON fields (`blocks`, `attachments`, `profile`) must be valid JSON strings.
- **Not included:** "Send and Wait for Response" from the n8n node — it relies on
  workflow suspend/resume, which a stateless Dify tool cannot replicate.

---

## How to use each function

## Message

### send_message — Send Message
**How to use:** Post a message to a channel, DM, or thread. Set `channel` and
`text` (or `blocks` for rich layout). To reply inside a thread, set `thread_ts`
to the parent message's `ts`.
`chat.postMessage` · **Token:** Bot · **Scope:** `chat:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Target channel ID, `#name`, or user ID (DM). |
| `text` | no* | Message text (Slack mrkdwn). *Required unless `blocks` is given. |
| `blocks` | no | Block Kit array (JSON string) for rich layout. |
| `attachments` | no | Legacy attachments array (JSON string). |
| `thread_ts` | no | Parent message `ts` to reply within its thread. |
| `reply_broadcast` | no | If threaded, also post to the channel. Default `false`. |
| `unfurl_links` | no | Enable link previews. Default `true`. |

**Returns:** `ts` (new message timestamp), `channel`.
**Example:** `channel=C012AB3CD`, `text=Deploy finished ✅`

### update_message — Update Message
**How to use:** Edit a message you sent. Provide the `channel` and the message
`ts`, plus the new `text` or `blocks`.
`chat.update` · **Token:** Bot · **Scope:** `chat:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID containing the message. |
| `ts` | yes | Timestamp of the message to edit. |
| `text` | no* | New text. *Required unless `blocks` is given. |
| `blocks` | no | New Block Kit array (JSON string). |
| `attachments` | no | New legacy attachments array (JSON string). |

**Returns:** updated `ts`, `text`.
**Example:** `channel=C012AB3CD`, `ts=1716999999.000200`, `text=Deploy rolled back`

### delete_message — Delete Message
**How to use:** Delete a message by its `channel` and `ts`.
`chat.delete` · **Token:** Bot · **Scope:** `chat:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID containing the message. |
| `ts` | yes | Timestamp of the message to delete. |

**Returns:** deleted `channel`, `ts`.

### get_permalink — Get Message Permalink
**How to use:** Get a shareable permanent URL for a message.
`chat.getPermalink` · **Token:** Bot · **Scope:** any valid token (bot must see the channel)

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID containing the message. |
| `message_ts` | yes | Timestamp of the message. |

**Returns:** `permalink` (also shown in the text summary).

### search_messages — Search Messages ⚠️
**How to use:** Full-text search across the workspace. Requires a User Token.
`search.messages` · **Token:** User ⚠️ · **Scope:** `search:read`

| Field | Required | Description |
|---|---|---|
| `query` | yes | Search query; supports operators (`from:`, `in:`, `has:`…). |
| `count` | no | Results per page (max 100). Default 20. |
| `page` | no | Page number. Default 1. |
| `sort` | no | `score` (relevance, default) or `timestamp`. |

**Returns:** `messages.matches[]`, `messages.total`.
**Example:** `query=from:@ada in:#general budget`

## Channel

### create_channel — Create Channel
**How to use:** Create a public or private channel by `name`.
`conversations.create` · **Token:** Bot · **Scope:** `channels:manage` (public) / `groups:write` (private)

| Field | Required | Description |
|---|---|---|
| `name` | yes | Channel name; lowercase, digits, `-`, `_` only. |
| `is_private` | no | Create a private channel. Default `false`. |

**Returns:** `channel.id`, `channel.name`.

### get_channel — Get Channel
**How to use:** Fetch a channel's metadata by ID.
`conversations.info` · **Token:** Bot · **Scope:** `channels:read` (`groups:read`, `im:read`, `mpim:read`)

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `include_num_members` | no | Include the member count. Default `false`. |

**Returns:** `channel` object (name, topic, purpose, creator, …).

### list_channels — List Channels
**How to use:** List conversations. Filter by `types`; page with `limit`/`cursor`.
`conversations.list` · **Token:** Bot · **Scope:** `channels:read` (+ `groups:read`, `im:read`, `mpim:read` per type)

| Field | Required | Description |
|---|---|---|
| `types` | no | CSV of `public_channel,private_channel,mpim,im`. Default `public_channel`. |
| `exclude_archived` | no | Omit archived channels. Default `true`. |
| `limit` | no | Per page (max 1000). Default 100. |
| `cursor` | no | Pagination cursor from a previous call. |

**Returns:** `channels[]`, `response_metadata.next_cursor`.

### channel_history — Get Channel History
**How to use:** Read a channel's messages, optionally bounded by `oldest`/`latest`.
`conversations.history` · **Token:** Bot · **Scope:** `channels:history` (`groups:history`, `im:history`, `mpim:history`)

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `oldest` | no | Only messages after this ts. |
| `latest` | no | Only messages before this ts. |
| `limit` | no | Per page (max 1000). Default 100. |
| `cursor` | no | Pagination cursor. |

**Returns:** `messages[]`, `has_more`.

### channel_replies — Get Thread Replies
**How to use:** Read replies to a threaded message. Provide `channel` and the
parent `ts`.
`conversations.replies` · **Token:** Bot · **Scope:** `channels:history` (per type)

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID containing the thread. |
| `ts` | yes | Parent (thread-root) message ts. |
| `limit` | no | Per page (max 1000). Default 100. |
| `cursor` | no | Pagination cursor. |

**Returns:** `messages[]` (parent first, then replies).

### invite_to_channel — Invite to Channel
**How to use:** Add one or more users to a channel.
`conversations.invite` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `users` | yes | CSV of user IDs (max 1000), e.g. `U111,U222`. |

**Returns:** the updated `channel` object.

### kick_from_channel — Remove from Channel
**How to use:** Remove a user from a channel.
`conversations.kick` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `user` | yes | User ID to remove. |

### join_channel — Join Channel
**How to use:** Have the bot join a public channel (needed before posting/reading
in many channels).
`conversations.join` · **Token:** Bot · **Scope:** `channels:join`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID to join. |

### leave_channel — Leave Channel
**How to use:** Have the bot leave a channel.
`conversations.leave` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID to leave. |

### open_channel — Open Conversation
**How to use:** Open or resume a DM / multi-person DM. Provide `users` to start a
new DM, or `channel` to resume an existing one.
`conversations.open` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| Field | Required | Description |
|---|---|---|
| `users` | no* | CSV of user IDs to open a DM/MPIM with. |
| `channel` | no* | Existing conversation ID to resume. *Provide `users` or `channel`. |
| `return_im` | no | Return the full conversation object. Default `false`. |

**Returns:** `channel.id` of the opened conversation.

### close_channel — Close Conversation
**How to use:** Close a DM or conversation.
`conversations.close` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Conversation ID to close. |

### archive_channel — Archive Channel
**How to use:** Archive a channel.
`conversations.archive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID to archive. |

### unarchive_channel — Unarchive Channel
**How to use:** Restore an archived channel.
`conversations.unarchive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID to unarchive. |

### list_channel_members — List Channel Members
**How to use:** List the user IDs in a channel; page with `limit`/`cursor`.
`conversations.members` · **Token:** Bot · **Scope:** `channels:read` / `groups:read`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `limit` | no | Per page (max 1000). Default 100. |
| `cursor` | no | Pagination cursor. |

**Returns:** `members[]` (user IDs), `response_metadata.next_cursor`.

### rename_channel — Rename Channel
**How to use:** Rename a channel.
`conversations.rename` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `name` | yes | New name (lowercase, no spaces). |

### set_channel_purpose — Set Channel Purpose
**How to use:** Set the channel's purpose (description).
`conversations.setPurpose` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `purpose` | yes | New purpose text. |

### set_channel_topic — Set Channel Topic
**How to use:** Set the channel's topic.
`conversations.setTopic` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID. |
| `topic` | yes | New topic text. |

## File

### upload_file — Upload File
**How to use:** Upload a file and optionally share it to a channel. Provide a
`file` input, or `content` text plus a `filename`. Uses Slack's current
three-step external-upload flow automatically.
`files.getUploadURLExternal` → upload → `files.completeUploadExternal` · **Token:** Bot · **Scope:** `files:write`

| Field | Required | Description |
|---|---|---|
| `file` | no* | The file to upload. |
| `content` | no* | Text content to upload as a file. *Provide `file` or `content`. |
| `filename` | no | Filename; defaults to the file's name or `upload`. |
| `title` | no | Display title in Slack. |
| `channel` | no | Channel ID to share the file to. |
| `initial_comment` | no | Message posted with the file. |
| `thread_ts` | no | Parent ts to share the file into that thread. |

**Returns:** the completed `files[]` entry including the new file `id`.
**Note:** the app must be a member of the target channel to share.

### get_file — Get File
**How to use:** Fetch a file's metadata by ID.
`files.info` · **Token:** Bot · **Scope:** `files:read`

| Field | Required | Description |
|---|---|---|
| `file` | yes | File ID (e.g. `F012AB3CD`). |

**Returns:** the `file` object (name, mimetype, url_private, …).

### list_files — List Files
**How to use:** List files, optionally filtered by channel, user, or type.
`files.list` · **Token:** Bot · **Scope:** `files:read`

| Field | Required | Description |
|---|---|---|
| `channel` | no | Only files in this channel. |
| `user` | no | Only files from this user. |
| `types` | no | CSV of `all,spaces,snippets,images,gdocs,zips,pdfs`. |
| `count` | no | Results per page. Default 100. |
| `page` | no | Page number. Default 1. |

**Returns:** `files[]`, `paging`.

## Reaction

### add_reaction — Add Reaction
**How to use:** Add an emoji reaction to a message.
`reactions.add` · **Token:** Bot · **Scope:** `reactions:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID of the message. |
| `timestamp` | yes | Message ts to react to. |
| `name` | yes | Emoji name without colons (e.g. `thumbsup`). |

### get_reactions — Get Reactions
**How to use:** List the reactions on a message.
`reactions.get` · **Token:** Bot · **Scope:** `reactions:read`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID of the message. |
| `timestamp` | yes | Message ts. |

**Returns:** `message.reactions[]` (name, count, users).

### remove_reaction — Remove Reaction
**How to use:** Remove an emoji reaction from a message.
`reactions.remove` · **Token:** Bot · **Scope:** `reactions:write`

| Field | Required | Description |
|---|---|---|
| `channel` | yes | Channel ID of the message. |
| `timestamp` | yes | Message ts. |
| `name` | yes | Emoji name without colons. |

## Star ⚠️ (User Token)

### add_star — Add Star ⚠️
**How to use:** Star a message or file for the authenticated user. Provide a
`file`, or both `channel` and `timestamp`.
`stars.add` · **Token:** User ⚠️ · **Scope:** `stars:write`

| Field | Required | Description |
|---|---|---|
| `channel` | no* | Channel ID (use with `timestamp`) to star a message. |
| `timestamp` | no* | Message ts (use with `channel`). |
| `file` | no* | File ID to star. *Provide `file`, or `channel` + `timestamp`. |

### remove_star — Remove Star ⚠️
**How to use:** Remove a star. Provide a `file`, or both `channel` and `timestamp`.
`stars.remove` · **Token:** User ⚠️ · **Scope:** `stars:write`

| Field | Required | Description |
|---|---|---|
| `channel` | no* | Channel ID (use with `timestamp`). |
| `timestamp` | no* | Message ts (use with `channel`). |
| `file` | no* | File ID. *Provide `file`, or `channel` + `timestamp`. |

### list_stars — List Stars ⚠️
**How to use:** List the authenticated user's starred items.
`stars.list` · **Token:** User ⚠️ · **Scope:** `stars:read`

| Field | Required | Description |
|---|---|---|
| `count` | no | Results per page. Default 100. |
| `page` | no | Page number. Default 1. |

**Returns:** `items[]`, `paging`.

## User

### get_user — Get User
**How to use:** Get information about a user by ID.
`users.info` · **Token:** Bot · **Scope:** `users:read`

| Field | Required | Description |
|---|---|---|
| `user` | yes | User ID (e.g. `U012AB3CD`). |

**Returns:** the `user` object (name, real_name, is_admin, tz, …).

### list_users — List Users
**How to use:** List all workspace members; page with `limit`/`cursor`.
`users.list` · **Token:** Bot · **Scope:** `users:read`

| Field | Required | Description |
|---|---|---|
| `limit` | no | Per page. Default 100. |
| `cursor` | no | Pagination cursor. |
| `include_locale` | no | Include each user's locale. Default `false`. |

**Returns:** `members[]`, `response_metadata.next_cursor`.

### get_user_profile — Get User Profile
**How to use:** Get a user's profile fields.
`users.profile.get` · **Token:** Bot · **Scope:** `users.profile:read` (or `users:read`)

| Field | Required | Description |
|---|---|---|
| `user` | yes | User ID whose profile to fetch. |
| `include_labels` | no | Include custom-field labels. Default `false`. |

**Returns:** the `profile` object (display_name, title, status_text, fields, …).

### get_user_presence — Get User Presence
**How to use:** Check whether a user is active or away.
`users.getPresence` · **Token:** Bot · **Scope:** `users:read`

| Field | Required | Description |
|---|---|---|
| `user` | yes | User ID whose presence to check. |

**Returns:** `presence` (`active` or `away`).

### update_user_profile — Update User Profile ⚠️
**How to use:** Update the authenticated user's profile (or another user's, as
admin). Provide a `profile` JSON object, or a single `name` + `value`.
`users.profile.set` · **Token:** User ⚠️ · **Scope:** `users.profile:write`

| Field | Required | Description |
|---|---|---|
| `profile` | no* | Object of profile fields to set (JSON string). |
| `name` | no* | A single field name (use with `value`). *Provide `profile`, or `name` + `value`. |
| `value` | no | Value for the single field. |
| `user` | no | Target user ID (admin only). Defaults to the token owner. |

**Example:** `profile={"status_text":"On leave","status_emoji":":palm_tree:"}`

## User Group

### create_usergroup — Create User Group
**How to use:** Create a user group.
`usergroups.create` · **Token:** Bot · **Scope:** `usergroups:write`

| Field | Required | Description |
|---|---|---|
| `name` | yes | Group name. |
| `handle` | no | Unique mention handle (without `@`). |
| `description` | no | Short description. |
| `channels` | no | CSV of default channel IDs. |

**Returns:** `usergroup.id`, `usergroup.name`.

### update_usergroup — Update User Group
**How to use:** Update a user group by its ID.
`usergroups.update` · **Token:** Bot · **Scope:** `usergroups:write`

| Field | Required | Description |
|---|---|---|
| `usergroup` | yes | User group ID (e.g. `S012AB3CD`). |
| `name` | no | New name. |
| `handle` | no | New mention handle. |
| `description` | no | New description. |
| `channels` | no | CSV of default channel IDs. |

### enable_usergroup — Enable User Group
**How to use:** Enable a disabled user group.
`usergroups.enable` · **Token:** Bot · **Scope:** `usergroups:write`

| Field | Required | Description |
|---|---|---|
| `usergroup` | yes | User group ID to enable. |

### disable_usergroup — Disable User Group
**How to use:** Disable a user group.
`usergroups.disable` · **Token:** Bot · **Scope:** `usergroups:write`

| Field | Required | Description |
|---|---|---|
| `usergroup` | yes | User group ID to disable. |

### list_usergroups — List User Groups
**How to use:** List the workspace's user groups.
`usergroups.list` · **Token:** Bot · **Scope:** `usergroups:read`

| Field | Required | Description |
|---|---|---|
| `include_disabled` | no | Include disabled groups. Default `false`. |
| `include_count` | no | Include member count per group. Default `false`. |
| `include_users` | no | Include member user IDs per group. Default `false`. |

**Returns:** `usergroups[]`.

---

## Common errors

| Slack `error` | Meaning / fix |
|---|---|
| `not_authed` / `invalid_auth` | Missing or wrong token. Re-check the credential. |
| `missing_scope` | The token lacks the required scope (the needed scope is appended to the message). Add it in the Slack app and reinstall. |
| `channel_not_found` | Bad channel ID, or the app isn't a member. Invite the app / use `join_channel`. |
| `not_in_channel` | The bot must join the channel first (`join_channel`). |
| user-token required | The operation needs the `Slack User Token`; add it in the plugin credentials. |
| `ratelimited` | Slack rate limit hit (HTTP 429). Retry after a short delay. |

See the full method reference at https://api.slack.com/methods.
