# Linear Trigger 插件

为 Dify 工作流提供 44 个 Linear Webhook 事件触发器的综合插件。监控并响应所有 Linear 事件,包括 Issues、评论、项目、周期、文档等。

## 功能

- **44 种事件类型**: 完整覆盖所有 Linear Webhook 事件
- **双重认证**: 同时支持 API 密钥和 OAuth 2.0
- **Webhook 签名验证**: 安全验证 Linear Webhook 请求
- **灵活过滤**: 按优先级、状态、名称、团队等过滤事件
- **丰富的事件数据**: 从 Linear Webhook 负载中提取详细信息

## 版本

**当前版本**: 0.3.0

## 可用事件（共 44 种）

### Issue 事件 (3)
- `issue_created`: 创建了新 Issue
- `issue_updated`: Issue 已更新
- `issue_removed`: Issue 已删除或归档

### Comment 事件 (3)
- `comment_created`: 添加了新评论
- `comment_updated`: 评论已编辑
- `comment_removed`: 评论已删除

### Project 事件 (3)
- `project_created`: 创建了新项目
- `project_updated`: 项目已更新
- `project_removed`: 项目已删除或归档

### Cycle 事件 (3)
- `cycle_created`: 创建了新周期
- `cycle_updated`: 周期已更新
- `cycle_removed`: 周期已删除或归档

### Document 事件 (3)
- `document_created`: 创建了新文档
- `document_updated`: 文档已更新
- `document_removed`: 文档已删除或归档

### Attachment 事件 (3)
- `attachment_created`: 添加了新附件
- `attachment_updated`: 附件已更新
- `attachment_removed`: 附件已删除

### IssueLabel 事件 (3)
- `issue_label_created`: 创建了新标签
- `issue_label_updated`: 标签已更新
- `issue_label_removed`: 标签已删除

### Reaction 事件 (3)
- `reaction_created`: 添加了新反应
- `reaction_updated`: 反应已更新
- `reaction_removed`: 反应已删除

### ProjectUpdate 事件 (3)
- `project_update_created`: 发布了新的项目更新
- `project_update_updated`: 项目更新已编辑
- `project_update_removed`: 项目更新已删除

### Initiative 事件 (3)
- `initiative_created`: 创建了新计划
- `initiative_updated`: 计划已更新
- `initiative_removed`: 计划已删除

### InitiativeUpdate 事件 (3)
- `initiative_update_created`: 发布了新的计划更新
- `initiative_update_updated`: 计划更新已编辑
- `initiative_update_removed`: 计划更新已删除

### Customer 事件 (3)
- `customer_created`: 创建了新客户
- `customer_updated`: 客户已更新
- `customer_removed`: 客户已删除

### CustomerNeed 事件 (3)
- `customer_need_created`: 创建了新的客户需求
- `customer_need_updated`: 客户需求已更新
- `customer_need_removed`: 客户需求已删除

### User 事件 (2)
- `user_created`: 添加了新用户
- `user_updated`: 用户已更新

### IssueRelation 事件 (3)
- `issue_relation_created`: 创建了新的 Issue 关联
- `issue_relation_updated`: Issue 关联已更新
- `issue_relation_removed`: Issue 关联已删除

## 快速开始
### 1. 认证和订阅选项

此插件支持 Linear Webhook 订阅和认证的**三种模式**。选择最适合您用例的选项：

#### 选项 1: OAuth 2.0（推荐）

**默认 OAuth 客户端（Dify Cloud）**
- 在 Dify Cloud 上，Linear 预配置了默认的 OAuth 客户端以实现一键授权。
- 选择 **Create with OAuth > Default** 并立即使用 Linear 授权 Dify。

**自定义 OAuth 客户端（自托管）**
- 在自托管环境中，您需要创建自己的 OAuth 应用程序。
- 选择 **Create with OAuth > Custom**。
- 转到 [Linear Settings > API Applications](https://linear.app/settings/api/applications) 并创建新的 OAuth 应用程序。
- 在 Linear 中创建 OAuth 应用程序时使用 Dify 提供的回调 URL。
- 返回 Dify，输入来自 Linear OAuth 应用程序的 Client ID 和 Client Secret，然后点击 **Save and Authorize**。
- 保存后，相同的客户端凭据可以重复用于将来的订阅。
- 指定订阅名称，选择要订阅的事件，并配置任何其他必需的设置。
- 我们建议选择所有可用事件。
- 点击 **Create**。

订阅配置页面上显示的 Callback URL 由 Dify 内部使用，代表您在 Linear 中创建 Webhook。您无需对此 URL 采取任何操作。

#### 选项 2: API 密钥认证

- 选择 **Create with API Key**。
- 转到 [Linear Settings > API](https://linear.app/settings/api) 并创建个人 API 密钥。
- 在 Dify 中输入 API 密钥，然后点击 **Verify**。
- 指定订阅名称，选择要订阅的事件，并配置任何其他必需的设置。
- 我们建议选择所有可用事件。
- 点击 **Create**。

#### 选项 3: 手动 Webhook 设置

- 选择 **Paste URL** 创建新订阅。
- 指定订阅名称，并使用提供的回调 URL 在 Linear 中手动创建 Webhook。
- 转到 Linear Workspace Settings > Webhooks，创建一个指向 Dify 回调 URL 的新 Webhook。
- （可选）在 Linear 中添加 Webhook 密钥以进行请求签名验证。
- （可选）测试创建的 Webhook：
  - Linear 在创建时通过向 Dify 发送 ping 请求来自动测试新 Webhook。
  - 您还可以触发订阅的事件，以便 Linear 向回调 URL 发送 HTTP 请求。
  - 检查 Manual Setup 页面上的 Request Logs 部分。如果 Webhook 正常工作，您将看到收到的请求和 Dify 的响应。
- 点击 **Create**。

**注意：**
- 为了获得最佳安全性和团队管理，建议使用 OAuth 2.0。
- Webhook Secret（在 Linear 中是可选的）启用请求签名验证以提供额外的安全性。

如果您不确定哪个选项符合您的需求，请参考 Dify 的插件配置页面或 Linear 文档以获取分步指导。

## 事件参数

每个事件都支持特定的过滤参数以减少噪音：

### 通用过滤器

- **title_contains/name_contains/body_contains**: 关键字过滤器（逗号分隔）
- **priority_filter**: 按优先级级别过滤（0-4）
- **state_filter**: 按工作流状态过滤
- **team_filter**: 按团队 ID 过滤
- **email_contains**: 按电子邮件模式过滤
- **emoji_filter**: 按特定表情符号过滤
- **issue_only**: 仅触发 Issue 相关项
- **project_only**: 仅触发项目相关项
- **status_changed**: 仅在状态更改时触发

## 支持

参考: [Linear Webhooks 文档](https://linear.app/developers/webhooks)
