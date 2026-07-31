# Slack Plugin for Dify

**Author:** langgenius · **Version:** 0.1.0 · **Type:** tool plugin

Slack Web API を通じて、Dify のエージェントやワークフローから Slack を自動化します。
**n8n の Slack ノード** との機能同等性を目指して構築されており、7 つのリソースにわたる 41 の操作を提供します。

---

## Setup

1. https://api.slack.com/apps で Slack アプリを作成します。
2. **OAuth & Permissions → Bot Token Scopes** で、必要なスコープを追加します
   （各機能の **Scope** を参照）。よい出発点となるセット:
   `chat:write`, `channels:read`, `channels:manage`, `channels:history`,
   `channels:join`, `groups:read`, `files:read`, `files:write`,
   `reactions:read`, `reactions:write`, `users:read`, `users.profile:read`,
   `usergroups:read`, `usergroups:write`。
3. アプリをワークスペースにインストールし、**Bot User OAuth Token**
   （`xoxb-…`）をコピーします。
4. *(任意)* **Search**、**Star**、**Update User Profile** を使う場合は、
   **User Token Scopes**（`search:read`, `stars:read`, `stars:write`,
   `users.profile:write`）を追加し、**User OAuth Token**（`xoxp-…`）をコピーします。
5. Dify で Slack プラグインを開き、認証情報を設定します:
   - **Slack Bot Token** — `xoxb-…` トークン（必須）
   - **Slack User Token** — `xoxp-…` トークン（任意）

---

## Conventions

- **Token** — 機能が使用する認証情報:
  - **Bot** — `Slack Bot Token`（`xoxb-…`）。
  - **User ⚠️** — 任意の `Slack User Token`（`xoxp-…`）。Slack はこれらの操作を
    bot トークンでは拒否します。ユーザートークンが設定されていない場合、機能は明確な
    エラーを返します。
- **Scope** — トークンが持つべき OAuth スコープ。チャンネル操作では正確なスコープは
  チャンネルの種類に依存します。一般的なものを示し、代替を括弧内に記載します。
- **Returns** — すべての機能は **JSON メッセージ**（Slack の生のレスポンス）と
  短い **テキストサマリー** を返します。失敗時にはエラー本文と
  `Slack error: <reason>` テキストメッセージを返します。
- **`channel`** は `C012AB3CD` のようなチャンネル ID（推奨）を受け付けます。一部の
  メソッドは `#channel-name` も受け付け、ユーザー ID（`U012AB3CD`）は DM を対象とします。
- **`ts` / `timestamp`** は Slack のメッセージタイムスタンプです。例: `1716999999.000200`。
- JSON フィールド（`blocks`, `attachments`, `profile`）は有効な JSON 文字列でなければなりません。
- **含まれないもの:** n8n ノードの "Send and Wait for Response"。これはワークフローの
  suspend/resume に依存しており、ステートレスな Dify ツールでは再現できません。

---

## How to use each function

## Message

### send_message — Send Message
**使い方:** チャンネル、DM、またはスレッドにメッセージを投稿します。`channel` と
`text`（またはリッチレイアウト用の `blocks`）を設定します。スレッド内に返信するには、
`thread_ts` を親メッセージの `ts` に設定します。
`chat.postMessage` · **Token:** Bot · **Scope:** `chat:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | 対象のチャンネル ID、`#name`、またはユーザー ID（DM）。 |
| `text` | 任意* | メッセージテキスト（Slack mrkdwn）。*`blocks` が指定されない限り必須。 |
| `blocks` | 任意 | リッチレイアウト用の Block Kit 配列（JSON 文字列）。 |
| `attachments` | 任意 | レガシーな attachments 配列（JSON 文字列）。 |
| `thread_ts` | 任意 | そのスレッド内に返信するための親メッセージの `ts`。 |
| `reply_broadcast` | 任意 | スレッド返信の場合、チャンネルにも投稿します。デフォルト `false`。 |
| `unfurl_links` | 任意 | リンクプレビューを有効にします。デフォルト `true`。 |

**戻り値:** `ts`（新しいメッセージのタイムスタンプ）、`channel`。
**例:** `channel=C012AB3CD`, `text=Deploy finished ✅`

### update_message — Update Message
**使い方:** 自分が送信したメッセージを編集します。`channel` とメッセージの
`ts`、および新しい `text` または `blocks` を指定します。
`chat.update` · **Token:** Bot · **Scope:** `chat:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | メッセージを含むチャンネル ID。 |
| `ts` | 必須 | 編集するメッセージのタイムスタンプ。 |
| `text` | 任意* | 新しいテキスト。*`blocks` が指定されない限り必須。 |
| `blocks` | 任意 | 新しい Block Kit 配列（JSON 文字列）。 |
| `attachments` | 任意 | 新しいレガシー attachments 配列（JSON 文字列）。 |

**戻り値:** 更新された `ts`、`text`。
**例:** `channel=C012AB3CD`, `ts=1716999999.000200`, `text=Deploy rolled back`

### delete_message — Delete Message
**使い方:** `channel` と `ts` を指定してメッセージを削除します。
`chat.delete` · **Token:** Bot · **Scope:** `chat:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | メッセージを含むチャンネル ID。 |
| `ts` | 必須 | 削除するメッセージのタイムスタンプ。 |

**戻り値:** 削除された `channel`、`ts`。

### get_permalink — Get Message Permalink
**使い方:** メッセージの共有可能な恒久 URL を取得します。
`chat.getPermalink` · **Token:** Bot · **Scope:** any valid token (bot must see the channel)

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | メッセージを含むチャンネル ID。 |
| `message_ts` | 必須 | メッセージのタイムスタンプ。 |

**戻り値:** `permalink`（テキストサマリーにも表示されます）。

### search_messages — Search Messages ⚠️
**使い方:** ワークスペース全体を全文検索します。User Token が必要です。
`search.messages` · **Token:** User ⚠️ · **Scope:** `search:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `query` | 必須 | 検索クエリ。演算子（`from:`, `in:`, `has:`…）をサポートします。 |
| `count` | 任意 | 1 ページあたりの結果数（最大 100）。デフォルト 20。 |
| `page` | 任意 | ページ番号。デフォルト 1。 |
| `sort` | 任意 | `score`（関連度、デフォルト）または `timestamp`。 |

**戻り値:** `messages.matches[]`、`messages.total`。
**例:** `query=from:@ada in:#general budget`

## Channel

### create_channel — Create Channel
**使い方:** `name` を指定してパブリックまたはプライベートチャンネルを作成します。
`conversations.create` · **Token:** Bot · **Scope:** `channels:manage` (public) / `groups:write` (private)

| フィールド | 必須 | 説明 |
|---|---|---|
| `name` | 必須 | チャンネル名。小文字、数字、`-`、`_` のみ。 |
| `is_private` | 任意 | プライベートチャンネルを作成します。デフォルト `false`。 |

**戻り値:** `channel.id`、`channel.name`。

### get_channel — Get Channel
**使い方:** ID を指定してチャンネルのメタデータを取得します。
`conversations.info` · **Token:** Bot · **Scope:** `channels:read` (`groups:read`, `im:read`, `mpim:read`)

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `include_num_members` | 任意 | メンバー数を含めます。デフォルト `false`。 |

**戻り値:** `channel` オブジェクト（name, topic, purpose, creator, …）。

### list_channels — List Channels
**使い方:** 会話を一覧表示します。`types` でフィルタし、`limit`/`cursor` でページングします。
`conversations.list` · **Token:** Bot · **Scope:** `channels:read` (+ `groups:read`, `im:read`, `mpim:read` per type)

| フィールド | 必須 | 説明 |
|---|---|---|
| `types` | 任意 | `public_channel,private_channel,mpim,im` の CSV。デフォルト `public_channel`。 |
| `exclude_archived` | 任意 | アーカイブ済みチャンネルを除外します。デフォルト `true`。 |
| `limit` | 任意 | 1 ページあたり（最大 1000）。デフォルト 100。 |
| `cursor` | 任意 | 前回の呼び出しから得たページングカーソル。 |

**戻り値:** `channels[]`、`response_metadata.next_cursor`。

### channel_history — Get Channel History
**使い方:** チャンネルのメッセージを読み取ります。任意で `oldest`/`latest` で範囲を限定できます。
`conversations.history` · **Token:** Bot · **Scope:** `channels:history` (`groups:history`, `im:history`, `mpim:history`)

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `oldest` | 任意 | この ts より後のメッセージのみ。 |
| `latest` | 任意 | この ts より前のメッセージのみ。 |
| `limit` | 任意 | 1 ページあたり（最大 1000）。デフォルト 100。 |
| `cursor` | 任意 | ページングカーソル。 |

**戻り値:** `messages[]`、`has_more`。

### channel_replies — Get Thread Replies
**使い方:** スレッド化されたメッセージへの返信を読み取ります。`channel` と親の
`ts` を指定します。
`conversations.replies` · **Token:** Bot · **Scope:** `channels:history` (per type)

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | スレッドを含むチャンネル ID。 |
| `ts` | 必須 | 親（スレッドルート）メッセージの ts。 |
| `limit` | 任意 | 1 ページあたり（最大 1000）。デフォルト 100。 |
| `cursor` | 任意 | ページングカーソル。 |

**戻り値:** `messages[]`（最初に親、その後に返信）。

### invite_to_channel — Invite to Channel
**使い方:** 1 人以上のユーザーをチャンネルに追加します。
`conversations.invite` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `users` | 必須 | ユーザー ID の CSV（最大 1000）。例: `U111,U222`。 |

**戻り値:** 更新された `channel` オブジェクト。

### kick_from_channel — Remove from Channel
**使い方:** ユーザーをチャンネルから削除します。
`conversations.kick` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `user` | 必須 | 削除するユーザー ID。 |

### join_channel — Join Channel
**使い方:** bot をパブリックチャンネルに参加させます（多くのチャンネルでは投稿/読み取り
の前に必要です）。
`conversations.join` · **Token:** Bot · **Scope:** `channels:join`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | 参加するチャンネル ID。 |

### leave_channel — Leave Channel
**使い方:** bot をチャンネルから退出させます。
`conversations.leave` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | 退出するチャンネル ID。 |

### open_channel — Open Conversation
**使い方:** DM / 複数人 DM を開くか再開します。新しい DM を開始するには `users` を、
既存のものを再開するには `channel` を指定します。
`conversations.open` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `users` | 任意* | DM/MPIM を開く相手のユーザー ID の CSV。 |
| `channel` | 任意* | 再開する既存の会話 ID。*`users` または `channel` を指定します。 |
| `return_im` | 任意 | 完全な会話オブジェクトを返します。デフォルト `false`。 |

**戻り値:** 開いた会話の `channel.id`。

### close_channel — Close Conversation
**使い方:** DM または会話を閉じます。
`conversations.close` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | 閉じる会話 ID。 |

### archive_channel — Archive Channel
**使い方:** チャンネルをアーカイブします。
`conversations.archive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | アーカイブするチャンネル ID。 |

### unarchive_channel — Unarchive Channel
**使い方:** アーカイブされたチャンネルを復元します。
`conversations.unarchive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | アーカイブ解除するチャンネル ID。 |

### list_channel_members — List Channel Members
**使い方:** チャンネル内のユーザー ID を一覧表示します。`limit`/`cursor` でページングします。
`conversations.members` · **Token:** Bot · **Scope:** `channels:read` / `groups:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `limit` | 任意 | 1 ページあたり（最大 1000）。デフォルト 100。 |
| `cursor` | 任意 | ページングカーソル。 |

**戻り値:** `members[]`（ユーザー ID）、`response_metadata.next_cursor`。

### rename_channel — Rename Channel
**使い方:** チャンネルの名前を変更します。
`conversations.rename` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `name` | 必須 | 新しい名前（小文字、スペースなし）。 |

### set_channel_purpose — Set Channel Purpose
**使い方:** チャンネルの purpose（説明）を設定します。
`conversations.setPurpose` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `purpose` | 必須 | 新しい purpose テキスト。 |

### set_channel_topic — Set Channel Topic
**使い方:** チャンネルの topic を設定します。
`conversations.setTopic` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | チャンネル ID。 |
| `topic` | 必須 | 新しい topic テキスト。 |

## File

### upload_file — Upload File
**使い方:** ファイルをアップロードし、任意でチャンネルに共有します。`file` 入力、
または `content` テキストと `filename` を指定します。Slack の現行の
3 ステップの外部アップロードフローを自動的に使用します。
`files.getUploadURLExternal` → upload → `files.completeUploadExternal` · **Token:** Bot · **Scope:** `files:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `file` | 任意* | アップロードするファイル。 |
| `content` | 任意* | ファイルとしてアップロードするテキストコンテンツ。*`file` または `content` を指定します。 |
| `filename` | 任意 | ファイル名。デフォルトはファイル名または `upload`。 |
| `title` | 任意 | Slack での表示タイトル。 |
| `channel` | 任意 | ファイルを共有するチャンネル ID。 |
| `initial_comment` | 任意 | ファイルとともに投稿されるメッセージ。 |
| `thread_ts` | 任意 | そのスレッドにファイルを共有するための親 ts。 |

**戻り値:** 完了した `files[]` エントリ（新しいファイル `id` を含む）。
**注意:** ファイルを共有するには、アプリが対象チャンネルのメンバーである必要があります。

### get_file — Get File
**使い方:** ID を指定してファイルのメタデータを取得します。
`files.info` · **Token:** Bot · **Scope:** `files:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `file` | 必須 | ファイル ID（例: `F012AB3CD`）。 |

**戻り値:** `file` オブジェクト（name, mimetype, url_private, …）。

### list_files — List Files
**使い方:** ファイルを一覧表示します。任意でチャンネル、ユーザー、または種類でフィルタできます。
`files.list` · **Token:** Bot · **Scope:** `files:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 任意 | このチャンネル内のファイルのみ。 |
| `user` | 任意 | このユーザーのファイルのみ。 |
| `types` | 任意 | `all,spaces,snippets,images,gdocs,zips,pdfs` の CSV。 |
| `count` | 任意 | 1 ページあたりの結果数。デフォルト 100。 |
| `page` | 任意 | ページ番号。デフォルト 1。 |

**戻り値:** `files[]`、`paging`。

## Reaction

### add_reaction — Add Reaction
**使い方:** メッセージに絵文字リアクションを追加します。
`reactions.add` · **Token:** Bot · **Scope:** `reactions:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | メッセージのチャンネル ID。 |
| `timestamp` | 必須 | リアクションを付けるメッセージの ts。 |
| `name` | 必須 | コロンなしの絵文字名（例: `thumbsup`）。 |

### get_reactions — Get Reactions
**使い方:** メッセージのリアクションを一覧表示します。
`reactions.get` · **Token:** Bot · **Scope:** `reactions:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | メッセージのチャンネル ID。 |
| `timestamp` | 必須 | メッセージの ts。 |

**戻り値:** `message.reactions[]`（name, count, users）。

### remove_reaction — Remove Reaction
**使い方:** メッセージから絵文字リアクションを削除します。
`reactions.remove` · **Token:** Bot · **Scope:** `reactions:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 必須 | メッセージのチャンネル ID。 |
| `timestamp` | 必須 | メッセージの ts。 |
| `name` | 必須 | コロンなしの絵文字名。 |

## Star ⚠️ (User Token)

### add_star — Add Star ⚠️
**使い方:** 認証されたユーザーのためにメッセージまたはファイルにスターを付けます。
`file`、または `channel` と `timestamp` の両方を指定します。
`stars.add` · **Token:** User ⚠️ · **Scope:** `stars:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 任意* | メッセージにスターを付けるチャンネル ID（`timestamp` とともに使用）。 |
| `timestamp` | 任意* | メッセージの ts（`channel` とともに使用）。 |
| `file` | 任意* | スターを付けるファイル ID。*`file`、または `channel` + `timestamp` を指定します。 |

### remove_star — Remove Star ⚠️
**使い方:** スターを削除します。`file`、または `channel` と `timestamp` の両方を指定します。
`stars.remove` · **Token:** User ⚠️ · **Scope:** `stars:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `channel` | 任意* | チャンネル ID（`timestamp` とともに使用）。 |
| `timestamp` | 任意* | メッセージの ts（`channel` とともに使用）。 |
| `file` | 任意* | ファイル ID。*`file`、または `channel` + `timestamp` を指定します。 |

### list_stars — List Stars ⚠️
**使い方:** 認証されたユーザーのスター付きアイテムを一覧表示します。
`stars.list` · **Token:** User ⚠️ · **Scope:** `stars:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `count` | 任意 | 1 ページあたりの結果数。デフォルト 100。 |
| `page` | 任意 | ページ番号。デフォルト 1。 |

**戻り値:** `items[]`、`paging`。

## User

### get_user — Get User
**使い方:** ID を指定してユーザーの情報を取得します。
`users.info` · **Token:** Bot · **Scope:** `users:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `user` | 必須 | ユーザー ID（例: `U012AB3CD`）。 |

**戻り値:** `user` オブジェクト（name, real_name, is_admin, tz, …）。

### list_users — List Users
**使い方:** ワークスペースの全メンバーを一覧表示します。`limit`/`cursor` でページングします。
`users.list` · **Token:** Bot · **Scope:** `users:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `limit` | 任意 | 1 ページあたり。デフォルト 100。 |
| `cursor` | 任意 | ページングカーソル。 |
| `include_locale` | 任意 | 各ユーザーのロケールを含めます。デフォルト `false`。 |

**戻り値:** `members[]`、`response_metadata.next_cursor`。

### get_user_profile — Get User Profile
**使い方:** ユーザーのプロフィールフィールドを取得します。
`users.profile.get` · **Token:** Bot · **Scope:** `users.profile:read` (or `users:read`)

| フィールド | 必須 | 説明 |
|---|---|---|
| `user` | 必須 | プロフィールを取得するユーザー ID。 |
| `include_labels` | 任意 | カスタムフィールドのラベルを含めます。デフォルト `false`。 |

**戻り値:** `profile` オブジェクト（display_name, title, status_text, fields, …）。

### get_user_presence — Get User Presence
**使い方:** ユーザーがアクティブか離席中かを確認します。
`users.getPresence` · **Token:** Bot · **Scope:** `users:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `user` | 必須 | プレゼンスを確認するユーザー ID。 |

**戻り値:** `presence`（`active` または `away`）。

### update_user_profile — Update User Profile ⚠️
**使い方:** 認証されたユーザーのプロフィール（または管理者として他のユーザーの
プロフィール）を更新します。`profile` JSON オブジェクト、または単一の `name` + `value` を指定します。
`users.profile.set` · **Token:** User ⚠️ · **Scope:** `users.profile:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `profile` | 任意* | 設定するプロフィールフィールドのオブジェクト（JSON 文字列）。 |
| `name` | 任意* | 単一のフィールド名（`value` とともに使用）。*`profile`、または `name` + `value` を指定します。 |
| `value` | 任意 | 単一フィールドの値。 |
| `user` | 任意 | 対象ユーザー ID（管理者のみ）。デフォルトはトークンの所有者。 |

**例:** `profile={"status_text":"On leave","status_emoji":":palm_tree:"}`

## User Group

### create_usergroup — Create User Group
**使い方:** ユーザーグループを作成します。
`usergroups.create` · **Token:** Bot · **Scope:** `usergroups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `name` | 必須 | グループ名。 |
| `handle` | 任意 | 一意のメンションハンドル（`@` なし）。 |
| `description` | 任意 | 短い説明。 |
| `channels` | 任意 | デフォルトチャンネル ID の CSV。 |

**戻り値:** `usergroup.id`、`usergroup.name`。

### update_usergroup — Update User Group
**使い方:** ID を指定してユーザーグループを更新します。
`usergroups.update` · **Token:** Bot · **Scope:** `usergroups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `usergroup` | 必須 | ユーザーグループ ID（例: `S012AB3CD`）。 |
| `name` | 任意 | 新しい名前。 |
| `handle` | 任意 | 新しいメンションハンドル。 |
| `description` | 任意 | 新しい説明。 |
| `channels` | 任意 | デフォルトチャンネル ID の CSV。 |

### enable_usergroup — Enable User Group
**使い方:** 無効化されたユーザーグループを有効にします。
`usergroups.enable` · **Token:** Bot · **Scope:** `usergroups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `usergroup` | 必須 | 有効にするユーザーグループ ID。 |

### disable_usergroup — Disable User Group
**使い方:** ユーザーグループを無効にします。
`usergroups.disable` · **Token:** Bot · **Scope:** `usergroups:write`

| フィールド | 必須 | 説明 |
|---|---|---|
| `usergroup` | 必須 | 無効にするユーザーグループ ID。 |

### list_usergroups — List User Groups
**使い方:** ワークスペースのユーザーグループを一覧表示します。
`usergroups.list` · **Token:** Bot · **Scope:** `usergroups:read`

| フィールド | 必須 | 説明 |
|---|---|---|
| `include_disabled` | 任意 | 無効化されたグループを含めます。デフォルト `false`。 |
| `include_count` | 任意 | グループごとのメンバー数を含めます。デフォルト `false`。 |
| `include_users` | 任意 | グループごとのメンバーのユーザー ID を含めます。デフォルト `false`。 |

**戻り値:** `usergroups[]`。

---

## Common errors

| Slack `error` | 意味 / 対処 |
|---|---|
| `not_authed` / `invalid_auth` | トークンが欠落しているか誤っています。認証情報を再確認してください。 |
| `missing_scope` | トークンに必要なスコープがありません（必要なスコープがメッセージに付加されます）。Slack アプリで追加して再インストールしてください。 |
| `channel_not_found` | チャンネル ID が誤っているか、アプリがメンバーではありません。アプリを招待するか `join_channel` を使用してください。 |
| `not_in_channel` | bot はまずチャンネルに参加する必要があります（`join_channel`）。 |
| user-token required | この操作には `Slack User Token` が必要です。プラグインの認証情報に追加してください。 |
| `ratelimited` | Slack のレート制限に達しました（HTTP 429）。少し待ってから再試行してください。 |

完全なメソッドリファレンスは https://api.slack.com/methods を参照してください。
