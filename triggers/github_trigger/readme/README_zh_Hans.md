GitHub Trigger（Webhooks）

概述

- GitHub Trigger 将仓库 Webhook 连接到 Dify，并分发 Issues、拉取请求、CI/CD 作业、安全警报等具体事件。
- 订阅可以自动配置：插件在选定的仓库上创建 Webhook，生成密钥并存储以供签名验证。
- 同时支持 OAuth（推荐）和个人访问令牌，因此管理员可以在按用户授权流程和共享 GitHub 凭据之间进行选择。
- 在 Dify 接收结果触发事件之前，会验证传入的负载（`X-Hub-Signature-256`、`X-GitHub-Event`）。

前提条件

- 对每个应该发出事件的仓库具有管理权限的 GitHub 用户。
- GitHub 可通过 HTTPS 访问的 Dify 实例（用于 Webhook 传递的公开访问端点）。
- 以下凭据选项之一：
  - GitHub OAuth App（客户端 ID/密钥，范围 `read:user admin:repo_hook`）。
  - 具有仓库管理权限的 GitHub 细粒度个人访问令牌 → **Repository hooks: Read & Write**。

分步设置

1. 在 Dify 中安装插件

- 选项：
  - 在 Plugin Center 中导入 `.difypkg`（Plugins → Import）。
  - 在开发期间，确保您的运行时从 `requirements.txt` 安装依赖项。

2. 选择身份验证策略（管理员）

- **OAuth（推荐）**：用户使用自己的 GitHub 身份进行授权，Dify 仅存储可刷新的访问令牌。
- **个人访问令牌**：管理员粘贴授予 Webhook 管理权限的 PAT；所有订阅共享相同的令牌。

3. （仅限 OAuth）创建 GitHub OAuth App

- GitHub Settings → Developer settings → OAuth Apps → **New OAuth App**  
  URL: https://github.com/settings/applications/new
  ![GitHub OAuth App](_assets/GITHUB_OAUTH_APP.png)

- 配置：
  - Application name: 任何描述性名称（例如，"Dify GitHub Trigger"）
  - Homepage URL: 您的 Dify 控制台 URL
  - Authorization callback URL: `https://<your-dify-host>/console/api/plugin/oauth/callback`
- 获取生成的 **Client ID** 和 **Client Secret**。
- 根据需要调整范围；插件默认为 `read:user admin:repo_hook`，允许在不完全访问仓库的情况下管理 Webhook。

4. 在 Dify 中输入凭据（管理员）

- OAuth 方式：
  - `client_id`: 来自 OAuth App。
  - `client_secret`: 来自 OAuth App。
  - `scope`（可选）：除非需要额外的 GitHub API，否则保持默认值。
- 个人访问令牌方式：
  - `access_tokens`: 粘贴 PAT；确保它具有上述仓库钩子权限。

5. 用户：创建订阅

- 点击 **Authorize**（OAuth）或确保已配置 PAT；插件将检索经过身份验证的账户可以管理的仓库。
- 从下拉列表中选择目标 `repository`（格式 `owner/repo`）。
- 选择一个或多个 Webhook `events`。默认值涵盖大多数仓库级别的活动；您可以缩小列表以减少噪音。
- （可选）如果手动维护 Webhook，请提供 `webhook_secret`。如果 Dify 配置 Webhook，则会自动生成密钥并与订阅一起存储。
- 手动 Webhook 设置：在 GitHub → Repository Settings → Webhooks 下，将 **Content type** 设置为 `application/json`。触发器仅接受原始 JSON 负载（`Content-Type: application/json`），并将拒绝 `application/x-www-form-urlencoded`。
- 保存订阅。Dify 显示用于手动设置或诊断的 Webhook 端点 URL（`https://<dify-host>/triggers/plugin/<subscription-id>`）。
    ![GitHub Webhook](_assets/GITHUB_WEBHOOK.png)

自动执行的操作

- 插件调用 GitHub 的 `repos/{owner}/{repo}/hooks` API 来创建（或稍后删除）Webhook，使用包含 `content_type=json` 和共享密钥的 JSON 负载。
- 当未提供时，使用 UUID4 十六进制字符串生成 Webhook 密钥，启用每次传递时的 HMAC SHA-256 签名验证（`X-Hub-Signature-256`）。
- 订阅刷新延长 Webhook TTL（约 30 天），因此 GitHub 无需重新授权即可保持其活动状态。
- 取消订阅时，通过 `DELETE repos/{owner}/{repo}/hooks/{hook_id}` 删除 Webhook。

支持的事件（概述）

- `issues`、`issue_comment`、`pull_request` 及相关的审查/评论事件。
- CI/CD 和自动化：`check_run`、`check_suite`、`workflow_run`、`workflow_job`、`deployment`、`deployment_status`。
- 仓库活动：`push`、`ref_change`（创建/删除）、`commit_comment`、`star`、`watch`、`fork`、`public`、`repository`。
- 项目和协作：`project`、`project_card`、`project_column`、`discussion`、`discussion_comment`、`label`、`milestone`、`member`。
- 安全和质量：`code_scanning_alert`、`dependabot_alert`、`repository_vulnerability_alert`、`secret_scanning`。
- 配置和治理：`branch_protection_configuration`、`branch_protection_rule`、`repository_ruleset`、`custom_property_values`。

工作原理

- 调度
  - 如果存在密钥，则验证 Webhook 签名。
  - 解析 JSON（或表单编码请求中的 `payload`）并捕获 `X-GitHub-Event`。
  - 将 GitHub 事件映射到具体的 Dify 事件名称（例如：`deployment_status` → `deployment_status_created`，`create/delete` → `ref_change`）。
  - 返回 JSON `{"status": "ok"}` 响应，以便 GitHub 认为传递成功。
- 事件
  - 每个事件 YAML 加载存储的负载，突出显示最相关的字段，并将它们作为下游工作流的结构化输出公开。
  - 基于操作的事件（例如发布已发布）会被拆分，以保持自动化清晰且确定性。


故障排除

- Webhook 创建失败：确认 OAuth 令牌或 PAT 具有 `admin:repo_hook` 范围，并且操作者是仓库的管理员。
- "缺少 Webhook 签名"：在订阅表单中提供密钥（对于手动 Webhook）或让 Dify 重新创建 Webhook。
- 没有事件到达：检查您的 Dify 端点是否公开可访问（状态 200），以及选定的事件是否与您期望的 GitHub 活动匹配。
- 401/403 响应：重新授权插件；已撤销的令牌或过期的 PAT 必须被替换。

参考资料

- GitHub Webhooks: https://docs.github.com/webhooks
- OAuth Apps: https://docs.github.com/apps/oauth-apps
- Event payloads: https://docs.github.com/webhooks-and-events/webhooks/webhook-events-and-payloads
