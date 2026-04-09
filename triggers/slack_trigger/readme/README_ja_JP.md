# Slack Trigger プラグインユーザーガイド

## このプラグインの機能

Slack Triggerプラグインは、DifyワークフローをSlackイベントと接続します。Slackワークスペースで何かが起こったとき - メッセージの受信、サブタスクの作成、チャンネルへの参加など - このプラグインは自動的にDifyワークフローを開始してこれらのイベントに応答します。

## 始め方

### ステップ1：Slackアプリをセットアップ

1. （オプション）[Slack Developer Portal](https://api.slack.com/apps)にアクセスして新しいアプリを作成するか、すでに持っているものを使用します。
   ![Slack App](./_assets/0462af05041885937e2004bcfe22e172.png)

2. アプリ設定で、次の5つの情報を見つけて保存します：
   - **App ID**: アプリを識別するために使用されるApp ID
   - **Signing Secret**: イベントデータを暗号化するために使用されます。Slackではオプションですが、このプラグインでは必須です
   - **Client ID**: アプリを識別するために使用されるClient ID
   - **Client Secret**: アプリを識別するために使用されるClient Secret
   - **Verification Token**: イベントデータを検証するために使用されるVerification Token

   ![Slack App Credentials](./_assets/cfabfa8ab301206ffcdd0249b6e4bbcd.png)

3. Difyプラグインページを開き、「Slack Trigger」プラグインを見つけ、Slackから取得した認証情報を使用して新しいサブスクリプションを作成します。

   ![Slack Trigger Plugin](./_assets/4f1a35b5dcf105e56c70064dfa3828c0.png)

   `Callback URL`をSlackの`Event Subscriptions`セクションに貼り付けると、ログが送信されます。

   ![Slack Event Subscriptions](./_assets/cd1ef2a58c9b8d572e27ba7a94240c97.png)

   ![Slack Request Logs](./_assets/5c3419d6ea28c14d4e1f7b5bde99b108.png)

4. 完了です。これで、ワークフローに`Slack Trigger`イベントを追加し、イベント駆動型ワークフローをお楽しみください！
