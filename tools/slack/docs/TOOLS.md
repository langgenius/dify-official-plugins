# Slack Plugin — Tool Reference

Complete reference for every tool in the Slack plugin. Tools are grouped by
resource, mirroring the n8n Slack node.

## Conventions

- **Token** — which credential the tool uses:
  - **Bot** — the `Slack Bot Token` (`xoxb-…`).
  - **User ⚠️** — the optional `Slack User Token` (`xoxp-…`). Slack rejects these
    operations with a bot token; the tool returns a clear error if no user token
    is configured.
- **Scope** — the OAuth scope(s) the token must have. For channel operations the
  exact scope depends on the channel type (public vs. private vs. DM); the most
  common one is listed, with alternates in parentheses.
- **Returns** — every tool yields a **JSON message** (the raw Slack API response)
  plus a short **text summary**. On failure it yields the JSON error body and a
  `Slack error: <reason>` text message. Only the notable response fields are
  documented below.
- **`channel`** accepts a channel ID such as `C012AB3CD` (recommended). Some
  methods also accept `#channel-name`. A user ID (`U012AB3CD`) opens/uses a DM.
- **`ts` / `timestamp`** is a Slack message timestamp, e.g. `1716999999.000200`.
- JSON parameters (blocks, attachments, profile) must be valid JSON strings.

---

## Message

### send_message — Send Message
Post a message to a channel, DM, or thread.
- **Method:** `chat.postMessage` · **Token:** Bot · **Scope:** `chat:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Target channel ID, `#name`, or user ID (DM). |
| `text` | string | no* | Message text (Slack mrkdwn). *Required unless `blocks` is given. |
| `blocks` | string (JSON) | no | Block Kit array for rich layout. |
| `attachments` | string (JSON) | no | Legacy attachments array. |
| `thread_ts` | string | no | Parent message `ts` to reply within its thread. |
| `reply_broadcast` | boolean | no | If threaded, also post to the channel. Default `false`. |
| `unfurl_links` | boolean | no | Enable link previews. Default `true`. |

**Returns:** `ts` (new message timestamp) and `channel`.
**Example:** `channel=C012AB3CD`, `text=Deploy finished ✅` →
posts the message and reports its `ts`.

### update_message — Update Message
Edit a previously sent message.
- **Method:** `chat.update` · **Token:** Bot · **Scope:** `chat:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID containing the message. |
| `ts` | string | yes | Timestamp of the message to edit. |
| `text` | string | no* | New text. *Required unless `blocks` is given. |
| `blocks` | string (JSON) | no | New Block Kit array. |
| `attachments` | string (JSON) | no | New legacy attachments array. |

**Returns:** the updated `ts` and `text`.
**Example:** `channel=C012AB3CD`, `ts=1716999999.000200`, `text=Deploy rolled back`.

### delete_message — Delete Message
Delete a message.
- **Method:** `chat.delete` · **Token:** Bot · **Scope:** `chat:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID containing the message. |
| `ts` | string | yes | Timestamp of the message to delete. |

**Returns:** the deleted `channel` and `ts`.

### get_permalink — Get Message Permalink
Get a permanent URL to a message.
- **Method:** `chat.getPermalink` · **Token:** Bot · **Scope:** any valid token (bot must be able to see the channel)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID containing the message. |
| `message_ts` | string | yes | Timestamp of the message. |

**Returns:** `permalink` (also echoed as the text summary).

### search_messages — Search Messages ⚠️
Full-text search across the workspace.
- **Method:** `search.messages` · **Token:** User ⚠️ · **Scope:** `search:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `query` | string | yes | Search query; supports Slack operators (`from:`, `in:`, `has:`…). |
| `count` | number | no | Results per page (max 100). Default 20. |
| `page` | number | no | Page number. Default 1. |
| `sort` | select | no | `score` (relevance, default) or `timestamp`. |

**Returns:** `messages.matches[]` and `messages.total`.
**Example:** `query=from:@ada in:#general budget`.

---

## Channel

### create_channel — Create Channel
Create a public or private channel.
- **Method:** `conversations.create` · **Token:** Bot · **Scope:** `channels:manage` (public) / `groups:write` (private)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Channel name; lowercase, digits, `-`, `_` only. |
| `is_private` | boolean | no | Create a private channel. Default `false`. |

**Returns:** `channel.id`, `channel.name`.

### get_channel — Get Channel
Fetch channel metadata.
- **Method:** `conversations.info` · **Token:** Bot · **Scope:** `channels:read` (`groups:read`, `im:read`, `mpim:read`)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `include_num_members` | boolean | no | Include member count. Default `false`. |

**Returns:** `channel` object (name, topic, purpose, creator, …).

### list_channels — List Channels
List conversations in the workspace.
- **Method:** `conversations.list` · **Token:** Bot · **Scope:** `channels:read` (+ `groups:read`, `im:read`, `mpim:read` per type)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `types` | string | no | CSV of `public_channel,private_channel,mpim,im`. Default `public_channel`. |
| `exclude_archived` | boolean | no | Omit archived channels. Default `true`. |
| `limit` | number | no | Per page (max 1000). Default 100. |
| `cursor` | string | no | Pagination cursor from a previous call. |

**Returns:** `channels[]` and `response_metadata.next_cursor` (for paging).

### channel_history — Get Channel History
Read a channel's messages.
- **Method:** `conversations.history` · **Token:** Bot · **Scope:** `channels:history` (`groups:history`, `im:history`, `mpim:history`)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `oldest` | string | no | Only messages after this ts. |
| `latest` | string | no | Only messages before this ts. |
| `limit` | number | no | Per page (max 1000). Default 100. |
| `cursor` | string | no | Pagination cursor. |

**Returns:** `messages[]` and `has_more`.

### channel_replies — Get Thread Replies
Read replies to a threaded message.
- **Method:** `conversations.replies` · **Token:** Bot · **Scope:** `channels:history` (per type)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID containing the thread. |
| `ts` | string | yes | Parent (thread-root) message ts. |
| `limit` | number | no | Per page (max 1000). Default 100. |
| `cursor` | string | no | Pagination cursor. |

**Returns:** `messages[]` (parent first, then replies).

### invite_to_channel — Invite to Channel
Add users to a channel.
- **Method:** `conversations.invite` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `users` | string | yes | CSV of user IDs (max 1000), e.g. `U111,U222`. |

**Returns:** the updated `channel` object.

### kick_from_channel — Remove from Channel
Remove a user from a channel.
- **Method:** `conversations.kick` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `user` | string | yes | User ID to remove. |

### join_channel — Join Channel
Join a public channel.
- **Method:** `conversations.join` · **Token:** Bot · **Scope:** `channels:join`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID to join. |

### leave_channel — Leave Channel
Leave a channel.
- **Method:** `conversations.leave` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID to leave. |

### open_channel — Open Conversation
Open or resume a DM / multi-person DM.
- **Method:** `conversations.open` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `users` | string | no* | CSV of user IDs to open a DM/MPIM with. |
| `channel` | string | no* | Existing conversation ID to resume. *Provide `users` or `channel`. |
| `return_im` | boolean | no | Return the full conversation object. Default `false`. |

**Returns:** `channel.id` of the opened conversation.

### close_channel — Close Conversation
Close a DM / conversation.
- **Method:** `conversations.close` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Conversation ID to close. |

### archive_channel — Archive Channel
Archive a channel.
- **Method:** `conversations.archive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID to archive. |

### unarchive_channel — Unarchive Channel
Restore an archived channel.
- **Method:** `conversations.unarchive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID to unarchive. |

### list_channel_members — List Channel Members
List the user IDs in a channel.
- **Method:** `conversations.members` · **Token:** Bot · **Scope:** `channels:read` / `groups:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `limit` | number | no | Per page (max 1000). Default 100. |
| `cursor` | string | no | Pagination cursor. |

**Returns:** `members[]` (user IDs) and `response_metadata.next_cursor`.

### rename_channel — Rename Channel
Rename a channel.
- **Method:** `conversations.rename` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `name` | string | yes | New name (lowercase, no spaces). |

### set_channel_purpose — Set Channel Purpose
Set the channel's purpose/description.
- **Method:** `conversations.setPurpose` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `purpose` | string | yes | New purpose text. |

### set_channel_topic — Set Channel Topic
Set the channel's topic.
- **Method:** `conversations.setTopic` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID. |
| `topic` | string | yes | New topic text. |

---

## File

### upload_file — Upload File
Upload a file and optionally share it to a channel. Uses Slack's current
three-step external-upload flow (`files.getUploadURLExternal` → PUT/POST the
bytes → `files.completeUploadExternal`).
- **Token:** Bot · **Scope:** `files:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file` | file | no* | The file to upload. |
| `content` | string | no* | Text content to upload as a file. *Provide `file` or `content`. |
| `filename` | string | no | Filename; defaults to the uploaded file's name or `upload`. |
| `title` | string | no | Display title in Slack. |
| `channel` | string | no | Channel ID to share the file to. |
| `initial_comment` | string | no | Message posted with the file. |
| `thread_ts` | string | no | Parent ts to share the file into that thread. |

**Returns:** the completed `files[]` entry including the new file `id`.
**Note:** requires the app to be a member of the target channel to share.

### get_file — Get File
Fetch file metadata.
- **Method:** `files.info` · **Token:** Bot · **Scope:** `files:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `file` | string | yes | File ID (e.g. `F012AB3CD`). |

**Returns:** the `file` object (name, mimetype, url_private, …).

### list_files — List Files
List files, optionally filtered.
- **Method:** `files.list` · **Token:** Bot · **Scope:** `files:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | no | Only files in this channel. |
| `user` | string | no | Only files from this user. |
| `types` | string | no | CSV of `all,spaces,snippets,images,gdocs,zips,pdfs`. |
| `count` | number | no | Results per page. Default 100. |
| `page` | number | no | Page number. Default 1. |

**Returns:** `files[]` and `paging`.

---

## Reaction

### add_reaction — Add Reaction
Add an emoji reaction to a message.
- **Method:** `reactions.add` · **Token:** Bot · **Scope:** `reactions:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID of the message. |
| `timestamp` | string | yes | Message ts to react to. |
| `name` | string | yes | Emoji name without colons (e.g. `thumbsup`). |

### get_reactions — Get Reactions
List the reactions on a message.
- **Method:** `reactions.get` · **Token:** Bot · **Scope:** `reactions:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID of the message. |
| `timestamp` | string | yes | Message ts. |

**Returns:** the `message.reactions[]` (name, count, users).

### remove_reaction — Remove Reaction
Remove an emoji reaction from a message.
- **Method:** `reactions.remove` · **Token:** Bot · **Scope:** `reactions:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | yes | Channel ID of the message. |
| `timestamp` | string | yes | Message ts. |
| `name` | string | yes | Emoji name without colons. |

---

## Star ⚠️ (User Token)

### add_star — Add Star ⚠️
Star a message or file for the authenticated user.
- **Method:** `stars.add` · **Token:** User ⚠️ · **Scope:** `stars:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | no* | Channel ID (use with `timestamp`) to star a message. |
| `timestamp` | string | no* | Message ts (use with `channel`). |
| `file` | string | no* | File ID to star. *Provide `file`, or both `channel` + `timestamp`. |

### remove_star — Remove Star ⚠️
Remove a star.
- **Method:** `stars.remove` · **Token:** User ⚠️ · **Scope:** `stars:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `channel` | string | no* | Channel ID (use with `timestamp`). |
| `timestamp` | string | no* | Message ts (use with `channel`). |
| `file` | string | no* | File ID. *Provide `file`, or both `channel` + `timestamp`. |

### list_stars — List Stars ⚠️
List the authenticated user's starred items.
- **Method:** `stars.list` · **Token:** User ⚠️ · **Scope:** `stars:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `count` | number | no | Results per page. Default 100. |
| `page` | number | no | Page number. Default 1. |

**Returns:** `items[]` and `paging`.

---

## User

### get_user — Get User
Get information about a user.
- **Method:** `users.info` · **Token:** Bot · **Scope:** `users:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user` | string | yes | User ID (e.g. `U012AB3CD`). |

**Returns:** the `user` object (name, real_name, is_admin, tz, …).

### list_users — List Users
List all workspace members.
- **Method:** `users.list` · **Token:** Bot · **Scope:** `users:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `limit` | number | no | Per page. Default 100. |
| `cursor` | string | no | Pagination cursor. |
| `include_locale` | boolean | no | Include each user's locale. Default `false`. |

**Returns:** `members[]` and `response_metadata.next_cursor`.

### get_user_profile — Get User Profile
Get a user's profile fields.
- **Method:** `users.profile.get` · **Token:** Bot · **Scope:** `users.profile:read` (or `users:read`)

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user` | string | yes | User ID whose profile to fetch. |
| `include_labels` | boolean | no | Include custom-field labels. Default `false`. |

**Returns:** the `profile` object (display_name, title, status_text, fields, …).

### get_user_presence — Get User Presence
Get a user's presence (active/away).
- **Method:** `users.getPresence` · **Token:** Bot · **Scope:** `users:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `user` | string | yes | User ID whose presence to check. |

**Returns:** `presence` (`active` or `away`).

### update_user_profile — Update User Profile ⚠️
Update the authenticated user's profile (or another user's, as admin).
- **Method:** `users.profile.set` · **Token:** User ⚠️ · **Scope:** `users.profile:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `profile` | string (JSON) | no* | Object of profile fields to set. |
| `name` | string | no* | A single field name (use with `value`). *Provide `profile`, or `name` + `value`. |
| `value` | string | no | Value for the single field. |
| `user` | string | no | Target user ID (admin only). Defaults to the token owner. |

**Example (set status):**
`profile={"status_text":"On leave","status_emoji":":palm_tree:"}`.

---

## User Group

### create_usergroup — Create User Group
Create a user group.
- **Method:** `usergroups.create` · **Token:** Bot · **Scope:** `usergroups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Group name. |
| `handle` | string | no | Unique mention handle (without `@`). |
| `description` | string | no | Short description. |
| `channels` | string | no | CSV of default channel IDs. |

**Returns:** `usergroup.id`, `usergroup.name`.

### update_usergroup — Update User Group
Update a user group.
- **Method:** `usergroups.update` · **Token:** Bot · **Scope:** `usergroups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `usergroup` | string | yes | User group ID (e.g. `S012AB3CD`). |
| `name` | string | no | New name. |
| `handle` | string | no | New mention handle. |
| `description` | string | no | New description. |
| `channels` | string | no | CSV of default channel IDs. |

### enable_usergroup — Enable User Group
Enable a disabled user group.
- **Method:** `usergroups.enable` · **Token:** Bot · **Scope:** `usergroups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `usergroup` | string | yes | User group ID to enable. |

### disable_usergroup — Disable User Group
Disable a user group.
- **Method:** `usergroups.disable` · **Token:** Bot · **Scope:** `usergroups:write`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `usergroup` | string | yes | User group ID to disable. |

### list_usergroups — List User Groups
List the workspace's user groups.
- **Method:** `usergroups.list` · **Token:** Bot · **Scope:** `usergroups:read`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `include_disabled` | boolean | no | Include disabled groups. Default `false`. |
| `include_count` | boolean | no | Include member count per group. Default `false`. |
| `include_users` | boolean | no | Include member user IDs per group. Default `false`. |

**Returns:** `usergroups[]`.

---

## Common errors

| Slack `error` | Meaning / fix |
|---|---|
| `not_authed` / `invalid_auth` | Missing or wrong token. Re-check the credential. |
| `missing_scope` | The token lacks the required scope (the tool appends the `needed` scope to the message). Add it in the Slack app and reinstall. |
| `channel_not_found` | Bad channel ID, or the app isn't a member. Invite the app / use `join_channel`. |
| `not_in_channel` | The bot must join the channel first (`join_channel`). |
| `user_token_required` (surfaced by this plugin) | The operation needs the `Slack User Token`; add it in the plugin credentials. |
| `ratelimited` | Slack rate limit hit (HTTP 429). Retry after a short delay. |

See the full method reference at https://api.slack.com/methods.
