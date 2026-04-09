# Telegram Trigger 插件示例

此示例演示如何构建一个 Trigger 插件，该插件仅使用机器人令牌自动注册 Telegram Bot API Webhook。`TelegramSubscriptionConstructor` 验证令牌，配置 Webhook（通过 `setWebhook`），并存储用于验证传入更新的密钥令牌。

## 功能
- 基于机器人令牌的订阅构造器（无需手动粘贴回调 URL）。
- 传入 Webhook 的密钥令牌验证。
- 涵盖所有 Telegram [Bot API 更新类型](https://core.telegram.org/bots/api#update)的事件，包括业务消息、反应、内联查询、支付、投票、成员变更和聊天提升。
- 镜像官方对象模式的结构化输出变量，因此可以直接在 Dify 工作流中使用。

## 开始使用
1. 使用 [BotFather](https://core.telegram.org/bots#botfather) 创建机器人并复制机器人令牌。
2. 在 Dify 中配置插件并选择 Telegram 触发器提供程序。
3. 在创建订阅期间提供机器人令牌；Webhook 会自动创建。
4. 将提供的任何事件（例如"Message Received"、"Inline Query Received"或"Chat Boost Updated"）添加到您的工作流中，以处理相应的更新。

有关触发器插件的更多详细信息，请参阅存储库文档和 `provider/telegram.py` 实现。
