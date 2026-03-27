# Dify 的 Zendesk Trigger 插件

一个基于 Webhook 的 Zendesk 综合触发器插件，可在 Dify 中实现智能自动化工作流。

## 概述

此插件通过 Webhook 触发器将 Zendesk 的客户服务平台与 Dify 的 AI 功能连接起来。它支持各种 Zendesk 事件，以实现智能客户服务自动化和知识库优化。

## 使用场景

### 1. 智能工单处理
- **场景**: 自动分析新工单并将其路由到合适的客服人员
- **触发器**: `ticket_created`
- **工作流**:
  - AI 分析工单内容、优先级和情绪
  - 根据专业知识推荐最合适的客服人员
  - 生成初始响应建议

### 2. SLA 监控和警报
- **场景**: 通过主动警报防止 SLA 违规
- **触发器**: `ticket_status_changed`、`ticket_priority_changed`
- **工作流**:
  - 监控工单状态转换
  - 接近 SLA 截止日期时发出警报
  - 触发自动升级

### 3. 知识库优化
- **场景**: 基于工单趋势改进帮助中心内容
- **触发器**: `article_published`、`article_unpublished`
- **工作流**:
  - 分析常见工单主题
  - 推荐知识库文章
  - 优化客服效率

## 支持的事件

### 工单事件
- **ticket_created**: 创建了新的支持工单
- **ticket_marked_as_spam**: Zendesk 将工单标记为垃圾邮件
- **ticket_status_changed**: 工单状态已更改（new → open → solved → closed）
- **ticket_priority_changed**: 工单优先级已修改（low → urgent）
- **ticket_comment_created**: 向工单添加了评论（公开或私密）

### 知识库事件
- **article_published**: 帮助中心文章已发布
- **article_unpublished**: 帮助中心文章已取消发布

## 配置

### 前提条件
1. 具有管理员访问权限的 Zendesk 账户
2. 来自 Zendesk Admin Center 的 API 令牌或 OAuth 客户端
3. Zendesk 子域（例如，acme.zendesk.com 的 `acme`）

### 设置步骤

1. **API 令牌配置**

![1](./_assets/1.png)

- 导航到 `Apps and integrations/Apis/Api tokens`
- 添加 API 令牌
- 将 api 配置到 dify

![2](./_assets/2.png)

2. **OAuth 客户端配置**

![3](./_assets/3.png)
![4](./_assets/4.png)

- oauth 客户端配置更复杂，让我们比较两个截图
- dify 中的 `Client ID` 是 Zendesk 中的 `Identifier`
- Zendesk 的 `Redirect URLs` 需要从 dify 复制
- Zendesk 的 `Client kind` 需要选择 `Confidential`

## 版本历史

- **1.0.0** (2025-10-31): 初始版本
  - 支持工单、评论和文章事件
  - 全面的过滤选项
  - Webhook 签名验证
  - 多语言支持（EN、ZH、JA）
