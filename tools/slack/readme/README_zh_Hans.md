# Slack Plugin for Dify

**作者：** an · **版本：** 0.0.1 · **类型：** 工具插件

通过 Slack Web API，从 Dify 智能体和工作流中自动化操作 Slack。其设计目标是与
**n8n Slack 节点** 功能对齐——涵盖 7 类资源、共 41 项操作。

---

## 安装设置

1. 在 https://api.slack.com/apps 创建一个 Slack 应用。
2. 在 **OAuth & Permissions → Bot Token Scopes** 下，添加你需要的权限范围
   （参见下方每个函数的 **Scope**）。一个不错的起始集合是：
   `chat:write`、`channels:read`、`channels:manage`、`channels:history`、
   `channels:join`、`groups:read`、`files:read`、`files:write`、
   `reactions:read`、`reactions:write`、`users:read`、`users.profile:read`、
   `usergroups:read`、`usergroups:write`。
3. 将应用安装到你的工作区，并复制 **Bot User OAuth Token**
   （`xoxb-…`）。
4. *（可选）* 对于 **搜索**、**收藏（Star）** 和 **更新用户资料**，请添加
   **User Token Scopes**（`search:read`、`stars:read`、`stars:write`、
   `users.profile:write`），并复制 **User OAuth Token**（`xoxp-…`）。
5. 在 Dify 中，打开 Slack 插件并设置凭据：
   - **Slack Bot Token** —— `xoxb-…` 令牌（必填）
   - **Slack User Token** —— `xoxp-…` 令牌（可选）

---

## 约定说明

- **Token** —— 函数使用哪个凭据：
  - **Bot** —— `Slack Bot Token`（`xoxb-…`）。
  - **User ⚠️** —— 可选的 `Slack User Token`（`xoxp-…`）。Slack 会拒绝使用 bot
    令牌执行这些操作；若未设置用户令牌，函数会返回明确的错误提示。
- **Scope** —— 令牌必须具备的 OAuth 权限范围。对于频道操作，具体所需的范围取决于
  频道类型；此处显示常用的范围，括号内为可替代的范围。
- **Returns** —— 每个函数都会产出一条 **JSON 消息**（Slack 的原始响应）
  以及一段简短的 **文本摘要**。失败时会产出错误正文和一条
  `Slack error: <reason>` 文本消息。
- **`channel`** 接受频道 ID，例如 `C012AB3CD`（推荐）；部分方法也接受
  `#channel-name`，而用户 ID（`U012AB3CD`）会指向一个私信（DM）。
- **`ts` / `timestamp`** 是 Slack 消息时间戳，例如 `1716999999.000200`。
- JSON 字段（`blocks`、`attachments`、`profile`）必须是有效的 JSON 字符串。
- **不包含：** n8n 节点中的 "Send and Wait for Response"——它依赖工作流的
  挂起/恢复，而无状态的 Dify 工具无法复现该行为。

---

## 各函数使用说明

## Message

### send_message — Send Message
**How to use：** 向频道、私信或线程发布一条消息。设置 `channel` 和
`text`（或使用 `blocks` 实现富文本布局）。若要在某个线程内回复，请将 `thread_ts`
设置为父消息的 `ts`。
`chat.postMessage` · **Token：** Bot · **Scope：** `chat:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 目标频道 ID、`#name` 或用户 ID（私信）。 |
| `text` | 否* | 消息文本（Slack mrkdwn）。*除非提供了 `blocks`，否则必填。 |
| `blocks` | 否 | 用于富文本布局的 Block Kit 数组（JSON 字符串）。 |
| `attachments` | 否 | 旧版 attachments 数组（JSON 字符串）。 |
| `thread_ts` | 否 | 父消息 `ts`，用于在其线程内回复。 |
| `reply_broadcast` | 否 | 若为线程回复，同时发布到频道。默认 `false`。 |
| `unfurl_links` | 否 | 启用链接预览。默认 `true`。 |

**Returns：** `ts`（新消息时间戳）、`channel`。
**Example：** `channel=C012AB3CD`、`text=Deploy finished ✅`

### update_message — Update Message
**How to use：** 编辑你发送过的消息。提供 `channel` 和消息的
`ts`，以及新的 `text` 或 `blocks`。
`chat.update` · **Token：** Bot · **Scope：** `chat:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 包含该消息的频道 ID。 |
| `ts` | 是 | 待编辑消息的时间戳。 |
| `text` | 否* | 新文本。*除非提供了 `blocks`，否则必填。 |
| `blocks` | 否 | 新的 Block Kit 数组（JSON 字符串）。 |
| `attachments` | 否 | 新的旧版 attachments 数组（JSON 字符串）。 |

**Returns：** 更新后的 `ts`、`text`。
**Example：** `channel=C012AB3CD`、`ts=1716999999.000200`、`text=Deploy rolled back`

### delete_message — Delete Message
**How to use：** 通过 `channel` 和 `ts` 删除一条消息。
`chat.delete` · **Token：** Bot · **Scope：** `chat:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 包含该消息的频道 ID。 |
| `ts` | 是 | 待删除消息的时间戳。 |

**Returns：** 已删除的 `channel`、`ts`。

### get_permalink — Get Message Permalink
**How to use：** 获取一条消息的可分享永久 URL。
`chat.getPermalink` · **Token：** Bot · **Scope：** 任意有效令牌（bot 必须能看到该频道）

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 包含该消息的频道 ID。 |
| `message_ts` | 是 | 该消息的时间戳。 |

**Returns：** `permalink`（也会显示在文本摘要中）。

### search_messages — Search Messages ⚠️
**How to use：** 在整个工作区进行全文搜索。需要 User Token。
`search.messages` · **Token：** User ⚠️ · **Scope：** `search:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `query` | 是 | 搜索查询；支持操作符（`from:`、`in:`、`has:`…）。 |
| `count` | 否 | 每页结果数（最多 100）。默认 20。 |
| `page` | 否 | 页码。默认 1。 |
| `sort` | 否 | `score`（相关性，默认）或 `timestamp`。 |

**Returns：** `messages.matches[]`、`messages.total`。
**Example：** `query=from:@ada in:#general budget`

## Channel

### create_channel — Create Channel
**How to use：** 通过 `name` 创建公开或私有频道。
`conversations.create` · **Token：** Bot · **Scope：** `channels:manage`（公开）/ `groups:write`（私有）

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 频道名称；仅限小写字母、数字、`-`、`_`。 |
| `is_private` | 否 | 创建私有频道。默认 `false`。 |

**Returns：** `channel.id`、`channel.name`。

### get_channel — Get Channel
**How to use：** 通过 ID 获取某个频道的元数据。
`conversations.info` · **Token：** Bot · **Scope：** `channels:read`（`groups:read`、`im:read`、`mpim:read`）

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `include_num_members` | 否 | 包含成员数量。默认 `false`。 |

**Returns：** `channel` 对象（name、topic、purpose、creator…）。

### list_channels — List Channels
**How to use：** 列出会话。通过 `types` 筛选；使用 `limit`/`cursor` 分页。
`conversations.list` · **Token：** Bot · **Scope：** `channels:read`（按类型另加 `groups:read`、`im:read`、`mpim:read`）

| 字段 | 必填 | 说明 |
|---|---|---|
| `types` | 否 | `public_channel,private_channel,mpim,im` 的 CSV。默认 `public_channel`。 |
| `exclude_archived` | 否 | 忽略已归档的频道。默认 `true`。 |
| `limit` | 否 | 每页数量（最多 1000）。默认 100。 |
| `cursor` | 否 | 上一次调用返回的分页游标。 |

**Returns：** `channels[]`、`response_metadata.next_cursor`。

### channel_history — Get Channel History
**How to use：** 读取某个频道的消息，可选地以 `oldest`/`latest` 限定范围。
`conversations.history` · **Token：** Bot · **Scope：** `channels:history`（`groups:history`、`im:history`、`mpim:history`）

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `oldest` | 否 | 仅返回此 ts 之后的消息。 |
| `latest` | 否 | 仅返回此 ts 之前的消息。 |
| `limit` | 否 | 每页数量（最多 1000）。默认 100。 |
| `cursor` | 否 | 分页游标。 |

**Returns：** `messages[]`、`has_more`。

### channel_replies — Get Thread Replies
**How to use：** 读取某条线程消息的回复。提供 `channel` 和
父消息的 `ts`。
`conversations.replies` · **Token：** Bot · **Scope：** `channels:history`（按类型）

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 包含该线程的频道 ID。 |
| `ts` | 是 | 父（线程根）消息的 ts。 |
| `limit` | 否 | 每页数量（最多 1000）。默认 100。 |
| `cursor` | 否 | 分页游标。 |

**Returns：** `messages[]`（先是父消息，然后是回复）。

### invite_to_channel — Invite to Channel
**How to use：** 将一个或多个用户添加到频道。
`conversations.invite` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `users` | 是 | 用户 ID 的 CSV（最多 1000 个），例如 `U111,U222`。 |

**Returns：** 更新后的 `channel` 对象。

### kick_from_channel — Remove from Channel
**How to use：** 将某个用户从频道中移除。
`conversations.kick` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `user` | 是 | 要移除的用户 ID。 |

### join_channel — Join Channel
**How to use：** 让 bot 加入一个公开频道（在许多频道中发布/读取前需要先加入）。
`conversations.join` · **Token：** Bot · **Scope：** `channels:join`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 要加入的频道 ID。 |

### leave_channel — Leave Channel
**How to use：** 让 bot 离开某个频道。
`conversations.leave` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 要离开的频道 ID。 |

### open_channel — Open Conversation
**How to use：** 打开或恢复一个私信 / 多人私信。提供 `users` 以发起
新私信，或提供 `channel` 以恢复现有会话。
`conversations.open` · **Token：** Bot · **Scope：** `im:write` / `mpim:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `users` | 否* | 用于开启私信/MPIM 的用户 ID 的 CSV。 |
| `channel` | 否* | 要恢复的现有会话 ID。*提供 `users` 或 `channel`。 |
| `return_im` | 否 | 返回完整的会话对象。默认 `false`。 |

**Returns：** 所打开会话的 `channel.id`。

### close_channel — Close Conversation
**How to use：** 关闭一个私信或会话。
`conversations.close` · **Token：** Bot · **Scope：** `im:write` / `mpim:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 要关闭的会话 ID。 |

### archive_channel — Archive Channel
**How to use：** 归档一个频道。
`conversations.archive` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 要归档的频道 ID。 |

### unarchive_channel — Unarchive Channel
**How to use：** 恢复一个已归档的频道。
`conversations.unarchive` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 要取消归档的频道 ID。 |

### list_channel_members — List Channel Members
**How to use：** 列出某个频道中的用户 ID；使用 `limit`/`cursor` 分页。
`conversations.members` · **Token：** Bot · **Scope：** `channels:read` / `groups:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `limit` | 否 | 每页数量（最多 1000）。默认 100。 |
| `cursor` | 否 | 分页游标。 |

**Returns：** `members[]`（用户 ID）、`response_metadata.next_cursor`。

### rename_channel — Rename Channel
**How to use：** 重命名一个频道。
`conversations.rename` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `name` | 是 | 新名称（小写，无空格）。 |

### set_channel_purpose — Set Channel Purpose
**How to use：** 设置频道的用途（描述）。
`conversations.setPurpose` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `purpose` | 是 | 新的用途文本。 |

### set_channel_topic — Set Channel Topic
**How to use：** 设置频道的主题。
`conversations.setTopic` · **Token：** Bot · **Scope：** `channels:manage` / `groups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 频道 ID。 |
| `topic` | 是 | 新的主题文本。 |

## File

### upload_file — Upload File
**How to use：** 上传文件，并可选地共享到某个频道。提供一个
`file` 输入，或提供 `content` 文本加上 `filename`。自动使用 Slack 当前的
三步式外部上传流程。
`files.getUploadURLExternal` → upload → `files.completeUploadExternal` · **Token：** Bot · **Scope：** `files:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `file` | 否* | 要上传的文件。 |
| `content` | 否* | 作为文件上传的文本内容。*提供 `file` 或 `content`。 |
| `filename` | 否 | 文件名；默认为文件本身的名称或 `upload`。 |
| `title` | 否 | 在 Slack 中显示的标题。 |
| `channel` | 否 | 要共享文件到的频道 ID。 |
| `initial_comment` | 否 | 随文件一起发布的消息。 |
| `thread_ts` | 否 | 父 ts，用于将文件共享到该线程中。 |

**Returns：** 已完成的 `files[]` 条目，包含新文件的 `id`。
**Note：** 应用必须是目标频道的成员才能共享。

### get_file — Get File
**How to use：** 通过 ID 获取某个文件的元数据。
`files.info` · **Token：** Bot · **Scope：** `files:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `file` | 是 | 文件 ID（例如 `F012AB3CD`）。 |

**Returns：** `file` 对象（name、mimetype、url_private…）。

### list_files — List Files
**How to use：** 列出文件，可选地按频道、用户或类型筛选。
`files.list` · **Token：** Bot · **Scope：** `files:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 否 | 仅此频道中的文件。 |
| `user` | 否 | 仅此用户的文件。 |
| `types` | 否 | `all,spaces,snippets,images,gdocs,zips,pdfs` 的 CSV。 |
| `count` | 否 | 每页结果数。默认 100。 |
| `page` | 否 | 页码。默认 1。 |

**Returns：** `files[]`、`paging`。

## Reaction

### add_reaction — Add Reaction
**How to use：** 为一条消息添加表情回应。
`reactions.add` · **Token：** Bot · **Scope：** `reactions:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 该消息所在的频道 ID。 |
| `timestamp` | 是 | 要回应的消息 ts。 |
| `name` | 是 | 不带冒号的表情名称（例如 `thumbsup`）。 |

### get_reactions — Get Reactions
**How to use：** 列出某条消息上的回应。
`reactions.get` · **Token：** Bot · **Scope：** `reactions:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 该消息所在的频道 ID。 |
| `timestamp` | 是 | 消息 ts。 |

**Returns：** `message.reactions[]`（name、count、users）。

### remove_reaction — Remove Reaction
**How to use：** 从一条消息中移除表情回应。
`reactions.remove` · **Token：** Bot · **Scope：** `reactions:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 是 | 该消息所在的频道 ID。 |
| `timestamp` | 是 | 消息 ts。 |
| `name` | 是 | 不带冒号的表情名称。 |

## Star ⚠️ (User Token)

### add_star — Add Star ⚠️
**How to use：** 为已认证用户收藏一条消息或一个文件。提供一个
`file`，或同时提供 `channel` 和 `timestamp`。
`stars.add` · **Token：** User ⚠️ · **Scope：** `stars:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 否* | 频道 ID（与 `timestamp` 搭配）以收藏一条消息。 |
| `timestamp` | 否* | 消息 ts（与 `channel` 搭配）。 |
| `file` | 否* | 要收藏的文件 ID。*提供 `file`，或 `channel` + `timestamp`。 |

### remove_star — Remove Star ⚠️
**How to use：** 移除一个收藏。提供一个 `file`，或同时提供 `channel` 和 `timestamp`。
`stars.remove` · **Token：** User ⚠️ · **Scope：** `stars:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `channel` | 否* | 频道 ID（与 `timestamp` 搭配）。 |
| `timestamp` | 否* | 消息 ts（与 `channel` 搭配）。 |
| `file` | 否* | 文件 ID。*提供 `file`，或 `channel` + `timestamp`。 |

### list_stars — List Stars ⚠️
**How to use：** 列出已认证用户的收藏项。
`stars.list` · **Token：** User ⚠️ · **Scope：** `stars:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `count` | 否 | 每页结果数。默认 100。 |
| `page` | 否 | 页码。默认 1。 |

**Returns：** `items[]`、`paging`。

## User

### get_user — Get User
**How to use：** 通过 ID 获取某个用户的信息。
`users.info` · **Token：** Bot · **Scope：** `users:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `user` | 是 | 用户 ID（例如 `U012AB3CD`）。 |

**Returns：** `user` 对象（name、real_name、is_admin、tz…）。

### list_users — List Users
**How to use：** 列出所有工作区成员；使用 `limit`/`cursor` 分页。
`users.list` · **Token：** Bot · **Scope：** `users:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `limit` | 否 | 每页数量。默认 100。 |
| `cursor` | 否 | 分页游标。 |
| `include_locale` | 否 | 包含每个用户的区域设置。默认 `false`。 |

**Returns：** `members[]`、`response_metadata.next_cursor`。

### get_user_profile — Get User Profile
**How to use：** 获取某个用户的资料字段。
`users.profile.get` · **Token：** Bot · **Scope：** `users.profile:read`（或 `users:read`）

| 字段 | 必填 | 说明 |
|---|---|---|
| `user` | 是 | 要获取资料的用户 ID。 |
| `include_labels` | 否 | 包含自定义字段标签。默认 `false`。 |

**Returns：** `profile` 对象（display_name、title、status_text、fields…）。

### get_user_presence — Get User Presence
**How to use：** 检查某个用户处于活跃还是离开状态。
`users.getPresence` · **Token：** Bot · **Scope：** `users:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `user` | 是 | 要检查在线状态的用户 ID。 |

**Returns：** `presence`（`active` 或 `away`）。

### update_user_profile — Update User Profile ⚠️
**How to use：** 更新已认证用户的资料（或以管理员身份更新其他用户的资料）。
提供一个 `profile` JSON 对象，或单个 `name` + `value`。
`users.profile.set` · **Token：** User ⚠️ · **Scope：** `users.profile:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `profile` | 否* | 要设置的资料字段对象（JSON 字符串）。 |
| `name` | 否* | 单个字段名称（与 `value` 搭配）。*提供 `profile`，或 `name` + `value`。 |
| `value` | 否 | 单个字段的值。 |
| `user` | 否 | 目标用户 ID（仅限管理员）。默认为令牌所有者。 |

**Example：** `profile={"status_text":"On leave","status_emoji":":palm_tree:"}`

## User Group

### create_usergroup — Create User Group
**How to use：** 创建一个用户组。
`usergroups.create` · **Token：** Bot · **Scope：** `usergroups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `name` | 是 | 组名称。 |
| `handle` | 否 | 唯一的提及句柄（不含 `@`）。 |
| `description` | 否 | 简短描述。 |
| `channels` | 否 | 默认频道 ID 的 CSV。 |

**Returns：** `usergroup.id`、`usergroup.name`。

### update_usergroup — Update User Group
**How to use：** 通过 ID 更新一个用户组。
`usergroups.update` · **Token：** Bot · **Scope：** `usergroups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `usergroup` | 是 | 用户组 ID（例如 `S012AB3CD`）。 |
| `name` | 否 | 新名称。 |
| `handle` | 否 | 新的提及句柄。 |
| `description` | 否 | 新的描述。 |
| `channels` | 否 | 默认频道 ID 的 CSV。 |

### enable_usergroup — Enable User Group
**How to use：** 启用一个已禁用的用户组。
`usergroups.enable` · **Token：** Bot · **Scope：** `usergroups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `usergroup` | 是 | 要启用的用户组 ID。 |

### disable_usergroup — Disable User Group
**How to use：** 禁用一个用户组。
`usergroups.disable` · **Token：** Bot · **Scope：** `usergroups:write`

| 字段 | 必填 | 说明 |
|---|---|---|
| `usergroup` | 是 | 要禁用的用户组 ID。 |

### list_usergroups — List User Groups
**How to use：** 列出工作区的用户组。
`usergroups.list` · **Token：** Bot · **Scope：** `usergroups:read`

| 字段 | 必填 | 说明 |
|---|---|---|
| `include_disabled` | 否 | 包含已禁用的组。默认 `false`。 |
| `include_count` | 否 | 包含每个组的成员数量。默认 `false`。 |
| `include_users` | 否 | 包含每个组的成员用户 ID。默认 `false`。 |

**Returns：** `usergroups[]`。

---

## 常见错误

| Slack `error` | 含义 / 解决办法 |
|---|---|
| `not_authed` / `invalid_auth` | 缺少或使用了错误的令牌。请重新检查凭据。 |
| `missing_scope` | 令牌缺少所需的权限范围（所需范围会附加在消息中）。请在 Slack 应用中添加并重新安装。 |
| `channel_not_found` | 频道 ID 错误，或应用不是频道成员。请邀请应用 / 使用 `join_channel`。 |
| `not_in_channel` | bot 必须先加入频道（`join_channel`）。 |
| user-token required | 该操作需要 `Slack User Token`；请在插件凭据中添加。 |
| `ratelimited` | 触发了 Slack 速率限制（HTTP 429）。请稍候片刻后重试。 |

完整方法参考请见 https://api.slack.com/methods。
