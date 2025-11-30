Gmail Trigger（Push + History）

概述

- Gmail Trigger 是一个 Dify 提供程序，通过 Cloud Pub/Sub 接收 Gmail 推送通知，并基于 Gmail History 发出具体事件：
  - `gmail_message_added`（新消息）
  - `gmail_message_deleted`（已删除的消息）
  - `gmail_label_added`（向消息添加标签）
  - `gmail_label_removed`（从消息中删除标签）
- 调度会验证/认证推送，提取一次历史增量，并拆分更改供事件使用。
- 注意：不支持使用 API 密钥访问 Gmail API。仅使用 OAuth（gmail.readonly）。

前提条件

- 已授权 Gmail API 的 Google 账户（在 OAuth 期间使用）
- 已启用 Pub/Sub API 的 Google Cloud 项目（由管理员在租户级别配置）

分步设置

1. 在 Dify 中安装插件

- 选项：
  - 如果打包为 `.difypkg`，在 Dify 的 Plugin Center 中导入（Plugins → Import）。
  - 对于开发期间的本地运行，确保运行时安装 `requirements.txt` 中的依赖项。

2. 配置 GCP 资源（管理员，一次性设置）

- 创建或选择将托管 Pub/Sub 资源的 Google Cloud 项目。确保以下 API 已启用 _（APIs & Services → Library）_：
  - Gmail API: https://console.cloud.google.com/apis/library/gmail.googleapis.com
  - Cloud Pub/Sub API: https://console.cloud.google.com/apis/library/pubsub.googleapis.com
- 创建专用服务账户并授予 Pub/Sub 权限：

  1. 转到 IAM & Admin → Service Accounts → **Create Service Account**。  
     Console URL: https://console.cloud.google.com/iam-admin/serviceaccounts

     截图：

     [![GCP Service Account](./_assets/GCP_SERVICE_ACCOUNT.png)](./_assets/GCP_SERVICE_ACCOUNT.png)

  2. 将 `roles/pubsub.admin` 角色分配给此服务账户，或选择"Pub/Sub Admin"角色，该角色已包含必要的权限（这是必需的，以便插件可以自动创建主题、订阅并更新 IAM 策略）。

     - 或者，自定义角色必须包括：`pubsub.topics.create`、`pubsub.topics.getIamPolicy`、`pubsub.topics.setIamPolicy`、`pubsub.subscriptions.create`、`pubsub.subscriptions.get`、`pubsub.subscriptions.delete`、`pubsub.subscriptions.list`。

       截图：

       [![GCP Permissions](./_assets/GCP_PERMISSION.png)](./_assets/GCP_PERMISSION.png)

  3. 为此服务账户创建 JSON 密钥并安全下载。
     截图：

     [![GCP Key](./_assets/GCP_KEY.png)](./_assets/GCP_KEY.png)

- 记下您的 Google Cloud **Project ID**（显示在项目仪表板或 IAM 页面上）。

3. 为插件配置 OAuth 客户端（管理员，一次性设置）

- 在 Google Cloud Console → APIs & Services → Credentials → **Create Credentials** → OAuth client ID。  
  Console URL: https://console.cloud.google.com/apis/credentials

  截图：

  [![GCP OAuth Client](./_assets/GC_OAUTH_CLIENT.png)](./_assets/GC_OAUTH_CLIENT.png)

  - Application type: **Web application**
  - Authorized redirect URIs: 复制在设置插件时 Dify 中显示的重定向 URI（例如：`https://<your-dify-host>/console/api/plugin/oauth/callback`）

- 获取生成的 **Client ID** 和 **Client Secret** 以供后用。

4. 在 Dify 中输入 OAuth 客户端参数

- 在插件配置表单中：
  - `client_id`: 上面创建的 OAuth 客户端 ID。
  - `client_secret`: 相应的客户端密钥。
  - `gcp_project_id`: 已启用 Pub/Sub 的 Google Cloud 项目 ID。
  - `gcp_service_account_json`: 粘贴为服务账户创建的完整 JSON 密钥（保持私密）。
- 当最终用户授权插件时，Dify 将自动派生每个用户的 Pub/Sub 主题。

5. 用户：授权并创建订阅

- 点击"Authorize"完成 OAuth（gmail.readonly 范围）
- 使用可选参数创建 Gmail 订阅：
  - `label_ids`（可选）：限定到特定标签（INBOX、UNREAD 等）
    - 文档：https://developers.google.com/gmail/api/reference/rest/v1/users.labels/list
  - Properties（可选，用于增强安全性）：
    - `require_oidc`: 强制执行 OIDC bearer 验证
    - `oidc_audience`: Webhook 端点 URL（自动填充）
    - `oidc_service_account_email`: 用于 Push 订阅的服务账户

自动执行的操作：

- 插件在您的 GCP 项目中创建/重用 Pub/Sub 主题
- 插件向主题授予 Gmail API 发布者权限
- 插件为此用户创建专用 Push 订阅
- 插件调用 Gmail `users.watch` API 开始监控
- 取消订阅时，插件清理 Push 订阅（主题保留以供重用）

OIDC 值的获取位置

- `oidc_audience`
  - 使用 Dify 订阅详细信息（Endpoint）中显示的确切 Webhook 端点 URL。例如：
    - `https://<your-dify-host>/triggers/plugin/<subscription-id>`
  - YAML 字段包含指向 Google 文档的 URL，用于 `audience` 声明：请参阅 OIDC 令牌参考。
- `oidc_service_account_email`
  - Pub/Sub 推送订阅使用的服务账户（通过 `--push-auth-service-account` 设置）。
  - 在 Google Cloud Console → IAM & Admin → Service Accounts 下找到它，或通过以下命令：
    - `gcloud iam service-accounts list --format='value(email)'`
  - YAML 字段链接到 Service Accounts 控制台页面。

工作原理

- 调度（触发器）
  - 可选择验证来自 Pub/Sub 推送的 OIDC bearer（iss/aud/email）
  - 解码 `message.data` 以获取 `historyId`/`emailAddress`
  - 调用 `users.history.list(startHistoryId=...)` 一次以收集增量
  - 按系列拆分更改，并将待处理批次存储在 Dify 存储中
  - 返回 Dify 要执行的具体事件名称列表
- 事件
  - 读取其系列的待处理批次
  - `gmail_message_added` 获取完整的消息元数据（标头、附件元数据）
  - 输出与事件 YAML `output_schema` 匹配

事件输出（概述）

- `gmail_message_added`
  - `history_id`: string
  - `messages[]`: id, threadId, internalDate, snippet, sizeEstimate, labelIds, headers{From,To,Subject,Date,Message-Id}, has_attachments, attachments[]
- `gmail_message_deleted`
  - `history_id`: string
  - `messages[]`: id, threadId
- `gmail_label_added` / `gmail_label_removed`
  - `history_id`: string
  - `changes[]`: id, threadId, labelIds

附件处理

- 触发器尝试上传最多 20 个真实附件（带有 `attachmentId` 或内联内容），跳过大于 5 MiB 的单个文件。
- `attachments[].file_url` 是唯一对外公开的下载地址；`attachments[].file_source` 标识其来源（原始链接为 `gmail`，Dify 镜像为 `dify_storage`）。
- 当附件成功上传到 Dify 时，会返回 `upload_file_id` 和 `original_url`（Gmail/Drive 原始地址）；如果未镜像，则省略 `original_url`。
- Gmail 经常为超大附件返回 Drive 链接，或直接在邮件正文中提供共享地址。事件会扫描文本/HTML 内容以提取这些链接，并将它们作为附件项返回，以供调用者统一处理。
- 调用者只需使用 `file_url`，根据 `file_source` 确定是直接访问 Gmail/Drive 还是通过 Dify 存储。

生命周期和刷新

- 创建：插件自动配置 Pub/Sub，然后使用 `topicName` 和可选的 `labelIds` 调用 `users.watch`
- 刷新：在过期前再次调用 `users.watch`（Gmail watch 有时间限制，约 7 天）
- 删除：调用 `users.stop` 并清理 Push 订阅

测试

- 向监视的邮箱（INBOX）发送电子邮件。您应该会看到 `gmail_message_added`
- 标记已读/未读（UNREAD 标签被删除/添加）会触发标签事件
- 删除电子邮件会触发 `gmail_message_deleted`
- 提示：您可以在 Pub/Sub 订阅详细信息中查看最近的传递；Dify 日志/控制台将显示触发器和事件跟踪。

故障排除

- 插件无法创建订阅：检查 OAuth 客户端参数中的 GCP 凭据是否正确配置
- 没有触发任何内容：验证您的 GCP 项目中是否启用了 Gmail API 和 Pub/Sub API
- 调度时出现 401/403：OIDC 设置不匹配；验证服务账户和受众
- `historyId` 过期：插件将检查点重置为最新通知并跳过该批次
- OAuth 问题：重新授权；确保已授予 gmail.readonly 范围

参考资料

- Gmail Push: https://developers.google.com/workspace/gmail/api/guides/push
- History: https://developers.google.com/gmail/api/reference/rest/v1/users.history/list
- Messages: https://developers.google.com/gmail/api/reference/rest/v1/users.messages/get
