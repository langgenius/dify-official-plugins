# Telegram Trigger プラグインの例

この例は、ボットトークンのみを使用してTelegram Bot API Webhookを自動的に登録するTriggerプラグインの構築方法を示しています。`TelegramSubscriptionConstructor`はトークンを検証し、Webhookをプロビジョニングし（`setWebhook`経由）、受信する更新を検証するために使用される秘密トークンを保存します。

## 機能
- ボットトークンベースのサブスクリプションコンストラクター（手動でのコールバックURL貼り付けは不要）。
- 受信Webhookの秘密トークン検証。
- ビジネスメッセージ、リアクション、インラインクエリ、支払い、投票、メンバーシップ変更、チャットブーストを含む、すべてのTelegram [Bot API更新タイプ](https://core.telegram.org/bots/api#update)のイベントカバレッジ。
- 公式オブジェクトスキーマをミラーリングする構造化出力変数により、Difyワークフローで直接使用できます。

## 始め方
1. [BotFather](https://core.telegram.org/bots#botfather)でボットを作成し、ボットトークンをコピーします。
2. Difyでプラグインを設定し、Telegramトリガープロバイダーを選択します。
3. サブスクリプション作成時にボットトークンを提供します；Webhookは自動的に作成されます。
4. 対応する更新を処理するために、提供されているイベント（例：「Message Received」、「Inline Query Received」、または「Chat Boost Updated」）のいずれかをワークフローに追加します。

トリガープラグインの詳細については、リポジトリドキュメントと`provider/telegram.py`の実装を参照してください。
