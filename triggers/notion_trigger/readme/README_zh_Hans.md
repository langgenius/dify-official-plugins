# Notion Trigger 插件

此插件通过订阅 Notion Webhook 使 Dify 能够响应实时 Notion 活动——包括页面、数据库、数据源和评论的更新。当您的 Notion 工作区中发生事件时，Notion 会安全地将事件负载 POST 到您配置的 Dify 端点。该插件将事件数据映射到 Dify 触发器变量中，因此您可以构建自动化或立即处理更改,而无需轮询。

在 [Notion API 文档](https://developers.notion.com/reference/webhooks)中了解有关 Notion Webhook 和支持的事件类型的更多信息。

## 配置 Webhook 订阅

1. 在 Notion 中，打开集成设置 → Webhooks → 创建订阅。
2. 将 Dify 提供的触发器端点粘贴为 Webhook URL。
3. 选择您希望 Notion 发出的事件类型。（稍后可以更改此列表。）
4. 提交表单。Notion 立即 POST 仅包含 `{"verification_token": "..."}` 的 JSON 负载。
5. 在 Dify 中，为此插件创建新的触发器连接,并将 `verification_token` 值粘贴到 Verification Token 字段中。可选择在 Event Filters 复选框列表中选择相同的事件类型,以仅将子集转发到工作流。
6. 返回 Notion 并点击 Verify。验证成功后，Notion 将开始向 Dify 传递完整的 Webhook 事件。

### 工作区过滤

每个事件定义都包含一个可选的 `workspace_filter` 参数。提供以逗号分隔的工作区 ID 列表,以仅将触发器限制为这些工作区。将字段留空以接受来自与订阅关联的任何工作区的事件。

## 支持的事件

### Page
- `page.created`
- `page.deleted`
- `page.undeleted`
- `page.content_updated`
- `page.moved`
- `page.properties_updated`
- `page.locked`
- `page.unlocked`

### Database
- `database.created`
- `database.content_updated`
- `database.deleted`
- `database.undeleted`
- `database.moved`
- `database.schema_updated`

### Data Source (API 版本 2025-09-03)
- `data_source.created`
- `data_source.deleted`
- `data_source.undeleted`
- `data_source.moved`
- `data_source.content_updated`
- `data_source.schema_updated`

### Comment
- `comment.created`
- `comment.updated`
- `comment.deleted`
