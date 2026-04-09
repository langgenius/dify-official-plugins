# Slack Trigger 插件用户指南

## 此插件的功能

Slack Trigger 插件将您的 Dify 工作流与 Slack 事件连接起来。当您的 Slack 工作区中发生某事时 - 例如收到消息、创建子任务或加入频道 - 此插件会自动启动您的 Dify 工作流来响应这些事件。

## 开始使用

### 步骤 1：设置您的 Slack 应用

1. （可选）转到 [Slack Developer Portal](https://api.slack.com/apps) 并创建一个新应用，或者您已经有一个了。
   ![Slack App](./_assets/0462af05041885937e2004bcfe22e172.png)

2. 在您的应用设置中，查找并保存以下五条信息：
   - **App ID**: 用于识别您应用的 App ID
   - **Signing Secret**: 用于加密事件数据，在 Slack 中是可选的，但在此插件中是必需的
   - **Client ID**: 用于识别您应用的 Client ID
   - **Client Secret**: 用于识别您应用的 Client Secret
   - **Verification Token**: 用于验证事件数据的 Verification Token

   ![Slack App Credentials](./_assets/cfabfa8ab301206ffcdd0249b6e4bbcd.png)

3. 打开您的 Dify 插件页面，找到"Slack Trigger"插件，使用从 Slack 获取的凭据创建新订阅。

   ![Slack Trigger Plugin](./_assets/4f1a35b5dcf105e56c70064dfa3828c0.png)

   将 `Callback URL` 粘贴到 Slack 的 `Event Subscriptions` 部分后，将向您发送日志。

   ![Slack Event Subscriptions](./_assets/cd1ef2a58c9b8d572e27ba7a94240c97.png)

   ![Slack Request Logs](./_assets/5c3419d6ea28c14d4e1f7b5bde99b108.png)

4. 完成，现在您可以将 `Slack Trigger` 事件添加到您的工作流中，尽情享受事件驱动的工作流吧！
