# Outlook

Dify 的 Microsoft Outlook 集成（通过 Microsoft Graph），支持**邮件和日历**：读取、发送和整理邮件，管理日历事件。

**版本：** 1.0.0

## 选择授权方式

| 方式 | 工具使用谁的邮箱 | 适用场景 |
|---|---|---|
| **OAuth** | 在 Dify 控制台登录的那一个人；所有使用工具的人共用这个邮箱 | 只处理一个固定邮箱的工作流或应用 |
| **Service Principal**（0.7.0） | 以应用身份访问指定的邮箱，没有用户登录 | 共享邮箱、服务邮箱的自动化 |
| **每个用户自己登录**（1.0.0） | 正在和 Agent 对话的那个人的邮箱；每个用户用自己的 Microsoft 账号登录一次 | 很多人一起用的对话 Agent（"我今天有什么日程？"） |

三种方式都使用同一个 Microsoft Entra 应用注册（见下面的第 1 步），可以同时存在：给插件添加多个授权，每个 Agent 或工作流节点各选一个。

## 功能

### 邮件
- **List Messages**：列出收件箱中的邮件。
- **Get Message**：按 ID 获取邮件详情，包括附件 ID。
- **Download Attachment**：下载邮件附件（需要 `message_id` 和 `attachment_id`），Dify 通过公开的 HTTPS 链接提供文件。
- **Send Message**：通过 Outlook 发送邮件，可带附件。
- **Send Draft**：发送草稿（需要 Draft Email 返回的草稿 ID）。
- **Draft Email**：创建草稿。
- **List Draft Emails**：列出草稿。
- **Add Attachment to Draft**：给草稿添加附件。
- **Prioritize Email**：设置邮件的重要性。
- **Flag Message**：给邮件加旗标或取消旗标。

### 日历
- **List Calendars**：列出日历。
- **List Events**：列出即将到来的事件，可指定某个日历。
- **Search Events**：按关键词和/或日期范围查找事件。
- List Events 和 Search Events 会显示每个事件的地点和在线会议链接（Teams，或邀请正文里的 Zoom / Google Meet / Webex 链接），Agent 不用逐个打开事件就能知道哪些是在线会议（1.0.0）。
- **List Calendar Groups**（0.7.0）：列出日历组，例如 *My Calendars* 和 *People's calendars*；别人共享给您的日历通常在后者。
- **日历组和共享日历**（0.7.0）：List Calendars、List Events、Search Events 支持可选的 **Calendar Group ID**，会覆盖组内所有日历，并标出每个事件所属的日历和所有者。需要 `Calendars.Read.Shared`。
- **Get Schedule**（0.7.0）：查询一段时间内一些人的忙闲，可按邮箱和/或日历组查询。组织内的任何人都能查，无需共享日历；只有您有权查看的事件才显示主题。
- **Create Event**：创建会议或约会（参会人、地点、Teams 在线会议）。
- **Get Event**、**Update Event**、**Delete Event**。

### 账号
- **Sign Out of Outlook**（`outlook_sign_out`，1.0.0）：仅限"每个用户自己登录"。清除当前用户的 Outlook 登录，用于切换账号。其他插件（例如 Teams）的登录不受影响。

## 第 1 步：在 Microsoft Entra ID 中注册应用

所有方式都需要一个应用注册。您需要一个能在租户中注册应用、并授予管理员同意的账号。

1. 打开 [Microsoft Entra 管理中心](https://entra.microsoft.com) → **App registrations** → **New registration**。

   ![New registration](../_assets/entra-new-registration.png)

2. 填写名称（例如 `Dify Outlook`），保持 **Single tenant only**。**Redirect URI** 选 **Web**：如果要用 OAuth，填入 Dify 显示的回调地址（见 [OAuth](#oauth)）；否则先留空，之后再添加。点击 **Register**。

   ![Register an application](../_assets/entra-register-form.png)

3. 在应用的 **Overview** 页面，复制 **Application (client) ID** 和 **Directory (tenant) ID**。

   ![Client ID 和 tenant ID](../_assets/entra-overview-ids.png)

4. 在 **API permissions** → **Add a permission** → **Microsoft Graph** 中，添加所用方式需要的权限：

   | 权限 | 类型 | 哪些方式需要 |
   |---|---|---|
   | `Mail.Read`、`Mail.ReadWrite`、`Mail.Send` | 委托（Delegated） | OAuth、每个用户自己登录 |
   | `Calendars.ReadWrite` | 委托 | OAuth、每个用户自己登录 |
   | `Calendars.Read.Shared` | 委托 | OAuth、每个用户自己登录（共享日历、Get Schedule） |
   | `offline_access` | 委托 | OAuth、每个用户自己登录（保持登录状态） |
   | `Mail.ReadWrite`、`Mail.Send`、`Calendars.ReadWrite` | 应用程序（Application） | Service Principal |

   新应用默认带有的 `User.Read` 可以保留。

5. 点击 **Grant admin consent for \<您的组织\>**，再点 **Yes** 确认。Service Principal 必须做这一步。"每个用户自己登录"也强烈建议做：这样用户不会看到授权同意页；如果浏览器里已经登录了 Microsoft，登录只需要点一下。

   ![授予管理员同意](../_assets/entra-grant-consent.png)

6. 在 **Certificates & secrets** → **Client secrets** 中点击 **New client secret**。立即复制 **Value**（它只显示一次）；**Secret ID** 不是密钥。

   ![New client secret](../_assets/entra-client-secret.png)

然后按您选择的方式继续配置。

## OAuth

1. 在 Dify 中打开 **插件** → **Outlook**，点击 **Add OAuth** 旁边的设置图标。

   ![OAuth 客户端设置按钮](../_assets/dify-oauth-client-button.png)

2. 对话框里会显示要使用的回调地址：把它添加到应用注册中（**Authentication** → **Add Redirect URI** → **Web**）。填写 **Client ID**、**Client Secret** 和 **Tenant ID**（个人账号或多租户可留空或填 `common`），选择 Microsoft Cloud，保存。

   ![OAuth 客户端设置](../_assets/dify-oauth-client-settings.png)

3. 点击 **Add OAuth**，用工具要使用其邮箱的那个 Microsoft 账号登录。

> 从 0.7.0 之前的版本升级会新增 `Calendars.Read.Shared` 权限：请把它加到应用注册中，并重新授权一次。

## Service Principal

适合以组织身份而不是个人身份运行的工作流：没有人需要登录，员工离职也不受影响，审计日志里显示的是应用。

1. 给应用添加第 1 步中的**应用程序**权限，并授予管理员同意。
2. 建议用 Exchange Online 的 [RBAC for Applications](https://learn.microsoft.com/exchange/permissions-exo/application-rbac) 把应用限制在需要的邮箱上，否则应用程序权限能访问租户里的所有邮箱。
3. 在 Dify 中点击 **Add API Key**，**Mode** 选 *Service Principal*，填写 **Tenant ID**（您的目录 ID，不能用 `common`）、**Client ID**、**Client Secret** 和 **Default Mailbox**（例如 `support@contoso.com`）。Dify 会登录并读取这个收件箱，以检查权限。
4. 每个工具都有可选的 **Mailbox** 设置（在节点里设置，LLM 无法选择），用同一个授权访问其他邮箱。

## 每个用户自己登录：个人 Outlook 助手

搭建一个 Agent，回答正在对话的那个人的"我的邮件里有什么？""我今天有什么日程？"。用户第一次需要 Outlook 时，Agent 会给出一个 Microsoft 登录链接。登录后，工具访问的就是该用户自己的邮箱和日历，之后的对话中也保持登录。

### 1. 创建登录回调 Endpoint

浏览器从 Microsoft 登录页返回时，会回到插件自己的 Endpoint。

1. 在 **插件** → **Outlook** 中滚动到 **ENDPOINTS**，点击 **+**。

   ![添加 Endpoint](../_assets/dify-endpoint-add.png)

2. 输入名称并保存，不需要填别的。

   ![Endpoint 名称](../_assets/dify-endpoint-name.png)

3. 用复制按钮复制 Endpoint 的 URL，格式是 `https://<您的 Dify 域名>/e/<id>/outlook/callback`。

   ![Endpoint URL](../_assets/dify-endpoint-url.png)

> **URL 以 `http://localhost` 开头？** 说明您自部署的 Dify 还在用默认的 `ENDPOINT_URL_TEMPLATE=http://localhost/e/{hook_id}`。Endpoint 实际在您的真实域名下可以访问，只是界面上显示的 URL 不对。可以在 `docker/.env` 中设置 `ENDPOINT_URL_TEMPLATE=https://<您的 Dify 域名>/e/{hook_id}` 并重启 API（`docker compose up -d api`），也可以手动把复制出来的 URL 里的 `http://localhost` 换成您的 Dify 地址。Microsoft 只允许 `localhost` 使用 `http`，所以 URL 必须是 `https`。
>
> ![显示为 localhost 的 Endpoint URL](../_assets/dify-endpoint-url-localhost.png)

### 2. 在 Microsoft 中登记 Endpoint URL

在应用注册中打开 **Authentication** → **Add Redirect URI** → **Web**，粘贴 Endpoint URL，点击 **Configure**。请确认填的是 `https` 地址而不是 `localhost`；如果对不上，Microsoft 登录页会报 `AADSTS50011` 错误。

![添加 Redirect URI](../_assets/entra-redirect-uri.png)

### 3. 在 Dify 中添加授权

1. 在 **插件** → **Outlook** 中点击 **Add API Key**。

   ![Add API Key](../_assets/dify-add-api-key.png)

2. 填写表单：
   - **Authorization Name**：任意名称，例如 `Dify Outlook Agent`。
   - **Mode**：*Each user signs in (own mailbox, for chat agents)*。
   - **Tenant ID**：您的目录（租户）ID。填写后只允许本组织的账号登录。
   - **Client ID** 和 **Client Secret**：第 1 步中获取的值。

   ![授权表单（上半部分）](../_assets/dify-per-user-form-top.png)

   - **Default Mailbox**：留空，这个方式不使用它。
   - **Sign-in Callback URL**：第 1 节中的 Endpoint URL。Dify 会拒绝 `localhost` 地址。
   - **Microsoft Cloud**：除非您的租户在国家云中，否则选 *Global*。

   ![授权表单（下半部分）](../_assets/dify-per-user-form-bottom.png)

   保存时，Dify 会检查这些字段；填写了具体的租户 ID 时，还会确认 Microsoft 接受这个 client ID 和 secret。这一步不会访问任何用户的邮箱，授权里也不保存任何用户的 token。

### 4. 配置 Agent

1. 创建一个 Agent，在 **TOOLS** 下点击 **Add**，添加 **Outlook**。保留需要的邮件和日历工具，以及 **Sign Out of Outlook**。
2. 在 Outlook 旁边的凭证菜单中，选择第 3 节添加的授权。如果选的是 OAuth 授权，工具访问的就是那一个共享邮箱，Sign Out of Outlook 也不会生效。

   ![选择授权](../_assets/agent-credential.png)

3. 提示词可以这样写：

   ```
   You can use the Outlook tools to access the current user's own mailbox and calendar.
   - When the user asks about their schedule or meetings, call list_events or search_events.
   - When the user asks about their email, call list_messages or get_message. Create a draft instead of sending unless the user clearly asks you to send.
   - If a tool says the user needs to sign in and returns a link, give the link to the user exactly as returned. Ask them to open it, sign in with their own Microsoft account, and reply "done" when finished. After they reply, call the same tool again.
   - Never make up emails or events. If a tool returns an error, tell the user what it says.
   - If the user asks to sign out or switch accounts, call outlook_sign_out.
   ```

4. 发布 Agent。

### 5. 用户看到的流程

1. 第一次提问会得到一个登录链接，15 分钟内有效。

   ![登录链接](../_assets/chat-sign-in-link.png)

2. 用户打开链接，用自己的 Microsoft 账号登录。

   ![选择账号](../_assets/chat-choose-account.png)

3. 页面显示 **Signed in**，提示用户回到对话里说一声已完成。页面上还会提醒：只有这次登录是自己发起的才继续；如果链接是别人发来的，可以在这里取消。
4. 用户回复 "done"，Agent 就用该用户自己的邮箱回答。登录后的第一个回答会注明使用的是哪个账号，登错账号也容易发现。

   ![用自己的邮箱回答](../_assets/chat-answer.png)

5. 说 "sign out" 会清除该用户的登录，下次提问时会重新要求登录。

   ![退出登录](../_assets/chat-sign-out.png)

### 用户能保持登录多久

access token 每小时在后台自动续期，Microsoft 的 refresh token 只要一直在用就保持有效（约 90 天不活动才过期），所以经常使用的用户通常只需要登录一次。升级插件不会让用户退出登录。以下情况会要求用户重新登录：

- **Dify 认为是另一个用户。** 插件按 Dify 的用户 ID 区分用户：
  - 在控制台中（调试和预览），是成员自己的账号，稳定不变。
  - 在**不需要登录的公开 WebApp** 中，每个浏览器（包括无痕窗口、清除 Cookie 之后）都是一个新的匿名用户，需要分别登录。
  - 通过 **Service API** 调用时，是调用方传入的 `user` 值，同一个人要一直传同一个值。调用方可以随意填写这个值，所以只能由已经验证过用户身份的可信后端调用 API。
  - 在 WebApp 的 URL 中传 `sys.user_id` 可以让 ID 保持不变，但任何人都能改 URL 冒充别的用户，只适合演示。
- 用户退出登录、修改密码，或者管理员撤销了该用户的会话或应用的授权。
- 组织的条件访问（Conditional Access）要求在一段时间后重新登录。
- **轮换了 client secret**：token 是用由它派生出的密钥加密的，所以所有人都要重新登录。

### 安全说明

- token 永远不会交给 Agent：工具结果里只有数据，没有 token，提示词注入也拿不到。每个用户的 token 都加密保存在插件存储中，不会写入日志。
- 一个用户不可能用到另一个用户的登录：用户 ID 来自 Dify，而不是 LLM。
- Endpoint 只会短暂保存一次性的授权码。把它换成 token 还需要 client secret 和 PKCE verifier，这两样 Endpoint 都没有。
- 用户可能把自己的登录链接发给同事。同事如果用这个链接登录，同事的邮箱就会连接到发链接那个人的对话里。**Signed in** 页面会提醒这一点，并提供 **cancel this sign-in** 链接。请告诉用户只通过自己请求的链接登录。管理员可以在 Entra 中撤销用户的会话，断开任何连接。
- 要一次断开所有人，可以轮换 client secret，或者在 Entra 中撤销应用的授权。

## 国家云

OAuth、Service Principal 和"每个用户自己登录"都有 **Microsoft Cloud** 设置：Global、US Government、US Government DoD 或 China（世纪互联）。它会同时切换登录地址和 Microsoft Graph 地址。已有的授权继续使用全球云。

## 使用方法

把 Outlook 工具添加到 Agent 或工作流中，填写输入并运行。日历的常见流程是 **List Calendars** → **Create Event** / **List Events**。

查看别人共享给您的日历（例如助理查看高管的日历）：**List Calendar Groups** → 取 *People's calendars* 的 ID → 用这个 Calendar Group ID 和日期范围调用 **Search Events**，或者用它调用 **Get Schedule** 查询忙闲。

## 输出变量

除了 `text` 和 `json`（与之前相同），每个工具还会返回带类型的变量，后续工作流节点可以直接选用，不必解析 `json`。每个工具都有 `success`（布尔值）和 `error`（字符串，成功时为空），工作流可以用 IF 节点分支；列表类工具返回扁平化的数组和 `count`。

| 工具 | 变量（`success`、`error` 之外） |
|---|---|
| List Messages | `messages`、`count` |
| Get Message | `message_id`、`conversation_id`、`subject`、`from_name`、`from_address`、`to`、`cc`、`received_datetime`、`body`、`body_type`、`web_link`、`attachment_ids`、`attachment_names` |
| Download Attachment | `file_name`、`content_type`、`size`、`downloaded` |
| Send Message | `subject`、`to`、`attachment_count` |
| Send Draft | `draft_id`、`subject` |
| Draft Email | `draft_id`、`subject`、`conversation_id`、`web_link` |
| List Draft Emails | `drafts`、`count` |
| Add Attachment to Draft | `attachments`、`count` |
| Prioritize Email | `message_id`、`importance` |
| Flag Email | `message_id`、`flag_status` |
| List Calendar Groups | `calendar_groups`、`count` |
| List Calendars | `calendars`、`count` |
| List Events | `events`、`count`、`errors` |
| Search Events | `events`、`count`、`errors` |
| Get Schedule (Free/Busy) | `schedules`、`busy_people`、`count` |
| Create Event | `event_id`、`subject`、`start`、`end`、`time_zone`、`location`、`web_link`、`online_meeting_url` |
| Get Event | `event_id`、`subject`、`start`、`end`、`time_zone`、`location`、`web_link`、`online_meeting_url` |
| Update Event | `event_id`、`subject`、`start`、`end`、`time_zone`、`location`、`web_link`、`online_meeting_url` |
| Delete Event | `event_id` |
| Sign Out of Outlook | `signed_out` |

## 常见问题

| 现象 | 原因和解决方法 |
|---|---|
| Microsoft 页面显示 `AADSTS50011: The redirect URI ... does not match` | 请求里的地址没有在应用中登记。在 **Authentication** → **Web** 中添加完全相同的地址。"每个用户自己登录"必须登记 `https` 的 Endpoint 地址，不能是 `localhost`。 |
| `AADSTS7000215` / client secret 无效 | 填写的应该是 secret 的 **Value**，不是 Secret ID；同时确认它没有过期。 |
| `OAuth credential for tool provider ... could not be refreshed` | Agent 或节点使用的 OAuth 授权已过期或被撤销。重新授权，或者换一个授权。 |
| Sign Out of Outlook 回复说这个凭证由整个工作区共享 | Agent 用的是 OAuth 或 Service Principal 授权。请改选"每个用户自己登录"的授权。 |
| 换一个浏览器又要求登录 | WebApp 是公开的，每个浏览器都是不同的匿名 Dify 用户。见[用户能保持登录多久](#用户能保持登录多久)。 |
| Endpoint URL 以 `http://localhost` 开头 | 设置 `ENDPOINT_URL_TEMPLATE`，见[第 1 节](#1-创建登录回调-endpoint)。 |
| Service Principal 访问某个邮箱时返回 403 | 应用程序权限没有授予管理员同意，或者 Exchange 的 RBAC for Applications 范围不包括这个邮箱。 |

## 隐私

本插件把所选操作的输入发送给 Microsoft Graph。使用"每个用户自己登录"时，会把每个用户的 token 加密保存在插件存储中。详见 [PRIVACY.md](../PRIVACY.md)。
