# Slack Plugin for Dify

**Author:** langgenius · **Version:** 0.1.0 · **Type:** tool plugin

Slack Web API를 통해 Dify 에이전트와 워크플로우에서 Slack을 자동화합니다.
**n8n Slack 노드**와의 기능 동등성을 목표로 제작되었으며, 7개 리소스에 걸쳐 41개의 작업을 제공합니다.

---

## Setup

1. https://api.slack.com/apps 에서 Slack 앱을 생성합니다.
2. **OAuth & Permissions → Bot Token Scopes** 에서 필요한 스코프를 추가합니다
   (각 함수의 **Scope** 참고). 좋은 시작 세트는 다음과 같습니다:
   `chat:write`, `channels:read`, `channels:manage`, `channels:history`,
   `channels:join`, `groups:read`, `files:read`, `files:write`,
   `reactions:read`, `reactions:write`, `users:read`, `users.profile:read`,
   `usergroups:read`, `usergroups:write`.
3. 앱을 워크스페이스에 설치하고 **Bot User OAuth Token**
   (`xoxb-…`)을 복사합니다.
4. *(선택)* **Search**, **Star**, **Update User Profile** 를 사용하려면
   **User Token Scopes** (`search:read`, `stars:read`, `stars:write`,
   `users.profile:write`)를 추가하고 **User OAuth Token** (`xoxp-…`)을 복사합니다.
5. Dify에서 Slack 플러그인을 열고 자격 증명을 설정합니다:
   - **Slack Bot Token** — `xoxb-…` 토큰 (필수)
   - **Slack User Token** — `xoxp-…` 토큰 (선택)

---

## Conventions

- **Token** — 함수가 사용하는 자격 증명:
  - **Bot** — `Slack Bot Token` (`xoxb-…`).
  - **User ⚠️** — 선택적 `Slack User Token` (`xoxp-…`). Slack은 봇 토큰으로는
    이러한 작업을 거부하며, 사용자 토큰이 설정되지 않은 경우 함수는 명확한 오류를 반환합니다.
- **Scope** — 토큰이 가져야 하는 OAuth 스코프. 채널 작업의 경우 정확한 스코프는
  채널 유형에 따라 달라지며, 일반적인 스코프를 괄호 안의 대안과 함께 표시합니다.
- **Returns** — 모든 함수는 **JSON 메시지**(원본 Slack 응답)와 짧은 **텍스트 요약**을
  산출합니다. 실패 시에는 오류 본문과 `Slack error: <reason>` 텍스트 메시지를 산출합니다.
- **`channel`** 은 `C012AB3CD` 같은 채널 ID를 받으며(권장), 일부 메서드는
  `#channel-name` 도 받고, 사용자 ID(`U012AB3CD`)는 DM을 대상으로 합니다.
- **`ts` / `timestamp`** 는 Slack 메시지 타임스탬프입니다. 예: `1716999999.000200`.
- JSON 필드(`blocks`, `attachments`, `profile`)는 유효한 JSON 문자열이어야 합니다.
- **미포함:** n8n 노드의 "Send and Wait for Response". 이는 워크플로우 일시 중단/재개에
  의존하는데, 상태를 유지하지 않는 Dify 도구로는 이를 재현할 수 없습니다.

---

## How to use each function

## Message

### send_message — Send Message
**사용법:** 채널, DM 또는 스레드에 메시지를 게시합니다. `channel` 과
`text`(또는 리치 레이아웃을 위한 `blocks`)를 설정합니다. 스레드 안에서 답장하려면
`thread_ts` 를 상위 메시지의 `ts` 로 설정합니다.
`chat.postMessage` · **Token:** Bot · **Scope:** `chat:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 대상 채널 ID, `#name`, 또는 사용자 ID (DM). |
| `text` | 선택* | 메시지 텍스트 (Slack mrkdwn). *`blocks` 가 주어지지 않으면 필수. |
| `blocks` | 선택 | 리치 레이아웃을 위한 Block Kit 배열 (JSON 문자열). |
| `attachments` | 선택 | 레거시 attachments 배열 (JSON 문자열). |
| `thread_ts` | 선택 | 해당 스레드 안에서 답장할 상위 메시지 `ts`. |
| `reply_broadcast` | 선택 | 스레드인 경우 채널에도 게시. 기본값 `false`. |
| `unfurl_links` | 선택 | 링크 미리보기 활성화. 기본값 `true`. |

**반환값:** `ts`(새 메시지 타임스탬프), `channel`.
**예시:** `channel=C012AB3CD`, `text=Deploy finished ✅`

### update_message — Update Message
**사용법:** 자신이 보낸 메시지를 편집합니다. `channel` 과 메시지 `ts`,
그리고 새 `text` 또는 `blocks` 를 제공합니다.
`chat.update` · **Token:** Bot · **Scope:** `chat:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 메시지가 포함된 채널 ID. |
| `ts` | 필수 | 편집할 메시지의 타임스탬프. |
| `text` | 선택* | 새 텍스트. *`blocks` 가 주어지지 않으면 필수. |
| `blocks` | 선택 | 새 Block Kit 배열 (JSON 문자열). |
| `attachments` | 선택 | 새 레거시 attachments 배열 (JSON 문자열). |

**반환값:** 업데이트된 `ts`, `text`.
**예시:** `channel=C012AB3CD`, `ts=1716999999.000200`, `text=Deploy rolled back`

### delete_message — Delete Message
**사용법:** `channel` 과 `ts` 로 메시지를 삭제합니다.
`chat.delete` · **Token:** Bot · **Scope:** `chat:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 메시지가 포함된 채널 ID. |
| `ts` | 필수 | 삭제할 메시지의 타임스탬프. |

**반환값:** 삭제된 `channel`, `ts`.

### get_permalink — Get Message Permalink
**사용법:** 메시지에 대해 공유 가능한 영구 URL을 가져옵니다.
`chat.getPermalink` · **Token:** Bot · **Scope:** any valid token (봇이 채널을 볼 수 있어야 함)

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 메시지가 포함된 채널 ID. |
| `message_ts` | 필수 | 메시지의 타임스탬프. |

**반환값:** `permalink`(텍스트 요약에도 표시됨).

### search_messages — Search Messages ⚠️
**사용법:** 워크스페이스 전체에 대한 전문 검색. User Token이 필요합니다.
`search.messages` · **Token:** User ⚠️ · **Scope:** `search:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `query` | 필수 | 검색 쿼리. 연산자(`from:`, `in:`, `has:`…)를 지원합니다. |
| `count` | 선택 | 페이지당 결과 수 (최대 100). 기본값 20. |
| `page` | 선택 | 페이지 번호. 기본값 1. |
| `sort` | 선택 | `score`(관련성, 기본값) 또는 `timestamp`. |

**반환값:** `messages.matches[]`, `messages.total`.
**예시:** `query=from:@ada in:#general budget`

## Channel

### create_channel — Create Channel
**사용법:** `name` 으로 공개 또는 비공개 채널을 생성합니다.
`conversations.create` · **Token:** Bot · **Scope:** `channels:manage` (공개) / `groups:write` (비공개)

| 필드 | 필수 | 설명 |
|---|---|---|
| `name` | 필수 | 채널 이름. 소문자, 숫자, `-`, `_` 만 허용. |
| `is_private` | 선택 | 비공개 채널 생성. 기본값 `false`. |

**반환값:** `channel.id`, `channel.name`.

### get_channel — Get Channel
**사용법:** ID로 채널의 메타데이터를 가져옵니다.
`conversations.info` · **Token:** Bot · **Scope:** `channels:read` (`groups:read`, `im:read`, `mpim:read`)

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `include_num_members` | 선택 | 멤버 수 포함. 기본값 `false`. |

**반환값:** `channel` 객체 (name, topic, purpose, creator, …).

### list_channels — List Channels
**사용법:** 대화 목록을 조회합니다. `types` 로 필터링하고 `limit`/`cursor` 로 페이지를 넘깁니다.
`conversations.list` · **Token:** Bot · **Scope:** `channels:read` (+ 유형별 `groups:read`, `im:read`, `mpim:read`)

| 필드 | 필수 | 설명 |
|---|---|---|
| `types` | 선택 | `public_channel,private_channel,mpim,im` 의 CSV. 기본값 `public_channel`. |
| `exclude_archived` | 선택 | 보관된 채널 제외. 기본값 `true`. |
| `limit` | 선택 | 페이지당 (최대 1000). 기본값 100. |
| `cursor` | 선택 | 이전 호출에서 얻은 페이지네이션 커서. |

**반환값:** `channels[]`, `response_metadata.next_cursor`.

### channel_history — Get Channel History
**사용법:** 채널의 메시지를 읽으며, 선택적으로 `oldest`/`latest` 로 범위를 제한합니다.
`conversations.history` · **Token:** Bot · **Scope:** `channels:history` (`groups:history`, `im:history`, `mpim:history`)

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `oldest` | 선택 | 이 ts 이후의 메시지만. |
| `latest` | 선택 | 이 ts 이전의 메시지만. |
| `limit` | 선택 | 페이지당 (최대 1000). 기본값 100. |
| `cursor` | 선택 | 페이지네이션 커서. |

**반환값:** `messages[]`, `has_more`.

### channel_replies — Get Thread Replies
**사용법:** 스레드 메시지의 답장을 읽습니다. `channel` 과
상위 `ts` 를 제공합니다.
`conversations.replies` · **Token:** Bot · **Scope:** `channels:history` (유형별)

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 스레드가 포함된 채널 ID. |
| `ts` | 필수 | 상위(스레드 루트) 메시지 ts. |
| `limit` | 선택 | 페이지당 (최대 1000). 기본값 100. |
| `cursor` | 선택 | 페이지네이션 커서. |

**반환값:** `messages[]`(상위 먼저, 그다음 답장).

### invite_to_channel — Invite to Channel
**사용법:** 한 명 이상의 사용자를 채널에 추가합니다.
`conversations.invite` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `users` | 필수 | 사용자 ID의 CSV (최대 1000). 예: `U111,U222`. |

**반환값:** 업데이트된 `channel` 객체.

### kick_from_channel — Remove from Channel
**사용법:** 채널에서 사용자를 제거합니다.
`conversations.kick` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `user` | 필수 | 제거할 사용자 ID. |

### join_channel — Join Channel
**사용법:** 봇이 공개 채널에 참여하도록 합니다(많은 채널에서 게시/읽기 전에 필요).
`conversations.join` · **Token:** Bot · **Scope:** `channels:join`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 참여할 채널 ID. |

### leave_channel — Leave Channel
**사용법:** 봇이 채널에서 나가도록 합니다.
`conversations.leave` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 나갈 채널 ID. |

### open_channel — Open Conversation
**사용법:** DM / 다중 사용자 DM을 열거나 재개합니다. 새 DM을 시작하려면 `users` 를,
기존 대화를 재개하려면 `channel` 을 제공합니다.
`conversations.open` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `users` | 선택* | DM/MPIM을 열 사용자 ID의 CSV. |
| `channel` | 선택* | 재개할 기존 대화 ID. *`users` 또는 `channel` 을 제공. |
| `return_im` | 선택 | 전체 대화 객체 반환. 기본값 `false`. |

**반환값:** 열린 대화의 `channel.id`.

### close_channel — Close Conversation
**사용법:** DM 또는 대화를 닫습니다.
`conversations.close` · **Token:** Bot · **Scope:** `im:write` / `mpim:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 닫을 대화 ID. |

### archive_channel — Archive Channel
**사용법:** 채널을 보관합니다.
`conversations.archive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 보관할 채널 ID. |

### unarchive_channel — Unarchive Channel
**사용법:** 보관된 채널을 복원합니다.
`conversations.unarchive` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 보관 해제할 채널 ID. |

### list_channel_members — List Channel Members
**사용법:** 채널의 사용자 ID를 조회하며, `limit`/`cursor` 로 페이지를 넘깁니다.
`conversations.members` · **Token:** Bot · **Scope:** `channels:read` / `groups:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `limit` | 선택 | 페이지당 (최대 1000). 기본값 100. |
| `cursor` | 선택 | 페이지네이션 커서. |

**반환값:** `members[]`(사용자 ID), `response_metadata.next_cursor`.

### rename_channel — Rename Channel
**사용법:** 채널 이름을 변경합니다.
`conversations.rename` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `name` | 필수 | 새 이름 (소문자, 공백 없음). |

### set_channel_purpose — Set Channel Purpose
**사용법:** 채널의 목적(설명)을 설정합니다.
`conversations.setPurpose` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `purpose` | 필수 | 새 목적 텍스트. |

### set_channel_topic — Set Channel Topic
**사용법:** 채널의 주제를 설정합니다.
`conversations.setTopic` · **Token:** Bot · **Scope:** `channels:manage` / `groups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 채널 ID. |
| `topic` | 필수 | 새 주제 텍스트. |

## File

### upload_file — Upload File
**사용법:** 파일을 업로드하고 선택적으로 채널에 공유합니다. `file` 입력을 제공하거나,
`content` 텍스트와 `filename` 을 제공합니다. Slack의 현재
3단계 외부 업로드 흐름을 자동으로 사용합니다.
`files.getUploadURLExternal` → upload → `files.completeUploadExternal` · **Token:** Bot · **Scope:** `files:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `file` | 선택* | 업로드할 파일. |
| `content` | 선택* | 파일로 업로드할 텍스트 콘텐츠. *`file` 또는 `content` 를 제공. |
| `filename` | 선택 | 파일명. 기본값은 파일의 이름 또는 `upload`. |
| `title` | 선택 | Slack에 표시되는 제목. |
| `channel` | 선택 | 파일을 공유할 채널 ID. |
| `initial_comment` | 선택 | 파일과 함께 게시되는 메시지. |
| `thread_ts` | 선택 | 해당 스레드로 파일을 공유할 상위 ts. |

**반환값:** 새 파일 `id` 를 포함하여 완료된 `files[]` 항목.
**참고:** 공유하려면 앱이 대상 채널의 멤버여야 합니다.

### get_file — Get File
**사용법:** ID로 파일의 메타데이터를 가져옵니다.
`files.info` · **Token:** Bot · **Scope:** `files:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `file` | 필수 | 파일 ID (예: `F012AB3CD`). |

**반환값:** `file` 객체 (name, mimetype, url_private, …).

### list_files — List Files
**사용법:** 파일 목록을 조회하며, 선택적으로 채널, 사용자 또는 유형으로 필터링합니다.
`files.list` · **Token:** Bot · **Scope:** `files:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 선택 | 이 채널의 파일만. |
| `user` | 선택 | 이 사용자의 파일만. |
| `types` | 선택 | `all,spaces,snippets,images,gdocs,zips,pdfs` 의 CSV. |
| `count` | 선택 | 페이지당 결과 수. 기본값 100. |
| `page` | 선택 | 페이지 번호. 기본값 1. |

**반환값:** `files[]`, `paging`.

## Reaction

### add_reaction — Add Reaction
**사용법:** 메시지에 이모지 반응을 추가합니다.
`reactions.add` · **Token:** Bot · **Scope:** `reactions:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 메시지의 채널 ID. |
| `timestamp` | 필수 | 반응할 메시지 ts. |
| `name` | 필수 | 콜론 없는 이모지 이름 (예: `thumbsup`). |

### get_reactions — Get Reactions
**사용법:** 메시지의 반응 목록을 조회합니다.
`reactions.get` · **Token:** Bot · **Scope:** `reactions:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 메시지의 채널 ID. |
| `timestamp` | 필수 | 메시지 ts. |

**반환값:** `message.reactions[]` (name, count, users).

### remove_reaction — Remove Reaction
**사용법:** 메시지에서 이모지 반응을 제거합니다.
`reactions.remove` · **Token:** Bot · **Scope:** `reactions:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 필수 | 메시지의 채널 ID. |
| `timestamp` | 필수 | 메시지 ts. |
| `name` | 필수 | 콜론 없는 이모지 이름. |

## Star ⚠️ (User Token)

### add_star — Add Star ⚠️
**사용법:** 인증된 사용자를 위해 메시지나 파일에 별표를 추가합니다.
`file` 을 제공하거나, `channel` 과 `timestamp` 를 모두 제공합니다.
`stars.add` · **Token:** User ⚠️ · **Scope:** `stars:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 선택* | 메시지에 별표를 추가할 채널 ID (`timestamp` 와 함께 사용). |
| `timestamp` | 선택* | 메시지 ts (`channel` 과 함께 사용). |
| `file` | 선택* | 별표를 추가할 파일 ID. *`file`, 또는 `channel` + `timestamp` 를 제공. |

### remove_star — Remove Star ⚠️
**사용법:** 별표를 제거합니다. `file` 을 제공하거나, `channel` 과 `timestamp` 를 모두 제공합니다.
`stars.remove` · **Token:** User ⚠️ · **Scope:** `stars:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `channel` | 선택* | 채널 ID (`timestamp` 와 함께 사용). |
| `timestamp` | 선택* | 메시지 ts (`channel` 과 함께 사용). |
| `file` | 선택* | 파일 ID. *`file`, 또는 `channel` + `timestamp` 를 제공. |

### list_stars — List Stars ⚠️
**사용법:** 인증된 사용자의 별표 항목을 조회합니다.
`stars.list` · **Token:** User ⚠️ · **Scope:** `stars:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `count` | 선택 | 페이지당 결과 수. 기본값 100. |
| `page` | 선택 | 페이지 번호. 기본값 1. |

**반환값:** `items[]`, `paging`.

## User

### get_user — Get User
**사용법:** ID로 사용자에 대한 정보를 가져옵니다.
`users.info` · **Token:** Bot · **Scope:** `users:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `user` | 필수 | 사용자 ID (예: `U012AB3CD`). |

**반환값:** `user` 객체 (name, real_name, is_admin, tz, …).

### list_users — List Users
**사용법:** 모든 워크스페이스 멤버를 조회하며, `limit`/`cursor` 로 페이지를 넘깁니다.
`users.list` · **Token:** Bot · **Scope:** `users:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `limit` | 선택 | 페이지당. 기본값 100. |
| `cursor` | 선택 | 페이지네이션 커서. |
| `include_locale` | 선택 | 각 사용자의 로케일 포함. 기본값 `false`. |

**반환값:** `members[]`, `response_metadata.next_cursor`.

### get_user_profile — Get User Profile
**사용법:** 사용자의 프로필 필드를 가져옵니다.
`users.profile.get` · **Token:** Bot · **Scope:** `users.profile:read` (또는 `users:read`)

| 필드 | 필수 | 설명 |
|---|---|---|
| `user` | 필수 | 프로필을 가져올 사용자 ID. |
| `include_labels` | 선택 | 사용자 지정 필드 레이블 포함. 기본값 `false`. |

**반환값:** `profile` 객체 (display_name, title, status_text, fields, …).

### get_user_presence — Get User Presence
**사용법:** 사용자가 활성 상태인지 부재 중인지 확인합니다.
`users.getPresence` · **Token:** Bot · **Scope:** `users:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `user` | 필수 | 상태를 확인할 사용자 ID. |

**반환값:** `presence` (`active` 또는 `away`).

### update_user_profile — Update User Profile ⚠️
**사용법:** 인증된 사용자의 프로필(또는 관리자로서 다른 사용자의 프로필)을 업데이트합니다.
`profile` JSON 객체를 제공하거나, 단일 `name` + `value` 를 제공합니다.
`users.profile.set` · **Token:** User ⚠️ · **Scope:** `users.profile:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `profile` | 선택* | 설정할 프로필 필드 객체 (JSON 문자열). |
| `name` | 선택* | 단일 필드 이름 (`value` 와 함께 사용). *`profile`, 또는 `name` + `value` 를 제공. |
| `value` | 선택 | 단일 필드의 값. |
| `user` | 선택 | 대상 사용자 ID (관리자 전용). 기본값은 토큰 소유자. |

**예시:** `profile={"status_text":"On leave","status_emoji":":palm_tree:"}`

## User Group

### create_usergroup — Create User Group
**사용법:** 사용자 그룹을 생성합니다.
`usergroups.create` · **Token:** Bot · **Scope:** `usergroups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `name` | 필수 | 그룹 이름. |
| `handle` | 선택 | 고유 멘션 핸들 (`@` 제외). |
| `description` | 선택 | 짧은 설명. |
| `channels` | 선택 | 기본 채널 ID의 CSV. |

**반환값:** `usergroup.id`, `usergroup.name`.

### update_usergroup — Update User Group
**사용법:** ID로 사용자 그룹을 업데이트합니다.
`usergroups.update` · **Token:** Bot · **Scope:** `usergroups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `usergroup` | 필수 | 사용자 그룹 ID (예: `S012AB3CD`). |
| `name` | 선택 | 새 이름. |
| `handle` | 선택 | 새 멘션 핸들. |
| `description` | 선택 | 새 설명. |
| `channels` | 선택 | 기본 채널 ID의 CSV. |

### enable_usergroup — Enable User Group
**사용법:** 비활성화된 사용자 그룹을 활성화합니다.
`usergroups.enable` · **Token:** Bot · **Scope:** `usergroups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `usergroup` | 필수 | 활성화할 사용자 그룹 ID. |

### disable_usergroup — Disable User Group
**사용법:** 사용자 그룹을 비활성화합니다.
`usergroups.disable` · **Token:** Bot · **Scope:** `usergroups:write`

| 필드 | 필수 | 설명 |
|---|---|---|
| `usergroup` | 필수 | 비활성화할 사용자 그룹 ID. |

### list_usergroups — List User Groups
**사용법:** 워크스페이스의 사용자 그룹을 조회합니다.
`usergroups.list` · **Token:** Bot · **Scope:** `usergroups:read`

| 필드 | 필수 | 설명 |
|---|---|---|
| `include_disabled` | 선택 | 비활성화된 그룹 포함. 기본값 `false`. |
| `include_count` | 선택 | 그룹별 멤버 수 포함. 기본값 `false`. |
| `include_users` | 선택 | 그룹별 멤버 사용자 ID 포함. 기본값 `false`. |

**반환값:** `usergroups[]`.

---

## Common errors

| Slack `error` | 의미 / 해결 |
|---|---|
| `not_authed` / `invalid_auth` | 토큰이 없거나 잘못됨. 자격 증명을 다시 확인하세요. |
| `missing_scope` | 토큰에 필요한 스코프가 없음(필요한 스코프가 메시지에 추가됨). Slack 앱에서 추가하고 다시 설치하세요. |
| `channel_not_found` | 잘못된 채널 ID이거나 앱이 멤버가 아님. 앱을 초대하거나 `join_channel` 을 사용하세요. |
| `not_in_channel` | 봇이 먼저 채널에 참여해야 함 (`join_channel`). |
| user-token required | 이 작업에는 `Slack User Token` 이 필요함. 플러그인 자격 증명에 추가하세요. |
| `ratelimited` | Slack 속도 제한에 도달함 (HTTP 429). 잠시 후 다시 시도하세요. |

전체 메서드 참조는 https://api.slack.com/methods 에서 확인하세요.
