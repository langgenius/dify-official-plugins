# RssHub Trigger 插件

通过简单的 Webhook 在 Dify 中接收 RssHub 订阅通知。灵活的事件、丰富的过滤器和可选的共享密钥验证。

**为什么使用此插件**

- 减少轮询：订阅源一更改就触发工作流。
- 规范化负载：传递标准 RSS/Atom 字段或自定义结构。
- 保持简单：可选的 API 密钥，无需服务器到服务器握手。

**什么是 RSS Hub？**

- RSS Hub 是一个为网站和服务生成 RSS/Atom 订阅源的开源项目。
- 项目主页（GitHub）: https://github.com/DIYgod/RSSHub
- 此插件是 Webhook 接收器：它接受 `feed_update` 负载并触发 Dify 工作流。

## 功能

- 可选的 API 密钥验证（标头或查询参数）
- 具有合理默认值的多个事件
- 丰富的每个事件过滤器以最小化噪音
- 作为触发变量的通用项目负载传递

## 架构

- 发送者：您的 RssHub 部署、读取订阅源的 cron/工作线程或将订阅源更新转换为 JSON POST 的任何脚本。
- 接收者：此插件的 Webhook URL（由 Dify 为触发器生成）。它（可选）验证并将事件分发到您的工作流。

## 设置

1. 将插件安装/导入到 Dify 中。
2. 订阅配置：
   - `API Key`（可选）：
     - 如果提供，所有 Webhook 调用必须包含相同的密钥（见认证）。
     - 如果留空，Webhook 接受未经身份验证的帖子。
3. 从您的 Dify 触发器复制生成的 Webhook 端点 URL。
4. 配置您的 RssHub（或小型伴侣工作线程）以将更新 POST 到此 URL。
    ![RSS_WEBHOOK.png](_assets/RSS_WEBHOOK.png)
   - 如果使用 API 密钥，请按如下所述包含它。
5. （可选）如果您通过标头/查询/正文发送自定义事件名称，它将被接受，但插件已针对 `feed_update` 进行了优化。

## 认证（可选）

- 在订阅中提供共享 `API Key` 以启用验证。
- 使用以下方式之一在每个请求中发送相同的密钥：
  - HTTP 标头 `X-Api-Key: <your_api_key>`（推荐）
  - HTTP 标头 `Authorization: Bearer <your_api_key>`
  - 查询字符串 `?token=<your_api_key>` 或 `?api_key=<your_api_key>`
- 如果您未在订阅中配置 API 密钥，接收器将接受未经身份验证的请求。

## 事件类型

- `feed_update`
  - 此插件使用单个事件 `feed_update`，并期望本 README 中描述的负载结构。
  - 参考（项目）: https://github.com/DIYgod/RSSHub
  - 其他自定义事件名称也被接受，但不是模式类型的。

## 负载模式（rss.app）

插件将整个 JSON 正文作为触发变量公开。规范模式为：

- `id`（string）：Webhook 事件的唯一标识符
- `type`（string）：事件类型（当前为 `feed_update`）
- `feed`（object）：订阅源元数据
  - `id`（string）：订阅源的唯一标识符
  - `title`（string）：订阅源标题
  - `source_url`（string）：源网站 URL
  - `rss_feed_url`（string）：RSS 订阅源 XML URL
  - `description`（string）：订阅源描述
  - `icon`（string）：网站图标/图标 URL
- `data`（object）：更新详细信息
  - `items_new`（对象数组）：自上次事件以来的新项目
    - `url`（string）
    - `title`（string）
    - `description_text`（string）
    - `thumbnail`（string）
    - `date_published`（日期字符串）
    - `authors`（对象数组）
      - `name`（string）
  - `items_changed`（对象数组）：自上次事件以来的更新项目
    - `url`（string）
    - `title`（string）
    - `description_text`（string）
    - `thumbnail`（string）
    - `date_published`（日期字符串）
    - `authors`（对象数组）
      - `name`（string）

## 提示和最佳实践

- 选择捕获您关心内容的最小过滤器集；让插件在上游忽略其余内容。
- 在通知程序端规范化 GUID/ID 以避免重复。
- 如果无法直接从 RssHub 推送，运行一个小型轮询器（cron/工作线程），将订阅源更改转换为 Webhook POST。
- 对于未经身份验证的模式，最好只允许已知源 IP 或在反向代理处使用秘密路径段。

## 故障排除

- 无运行：检查事件类型和过滤器；尝试删除过滤器以验证连接。
- 使用 API 密钥时出现 401/403：确保订阅的 `API Key` 与您发送的标头/查询匹配。
- 400 解析错误：确保 `Content-Type: application/json` 或使用包含 `payload` JSON 字段的 URL 编码发送。
- 事件不匹配：明确指定事件（标头或查询）以避免启发式回退。

## 限制

- 此插件不创建/管理 RssHub 订阅。从您的部署或伴侣工作线程配置推送。
- 仅支持共享密钥样式验证；目前没有 OAuth/HMAC。
