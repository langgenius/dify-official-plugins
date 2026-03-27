# Typeform Trigger プラグイン

Typeformの`form_response` Webhookをリスンするdifyトリガープラグイン。各送信は完全なレスポンスペイロードとともにワークフローに転送されるため、リアルタイムでフォローアップアクションを自動化できます。

## クイックスタート

1. Difyワークスペースにプラグインをインストールし、ワークフローにトリガーをドラッグします。
2. 接続方法を選択します（手動Webhook、Personal Access Token、またはOAuth）。
3. リスンしたいTypeformを選択します（API Key / OAuthモードでは必須、手動の場合はオプションのフィルター）。
4. ワークフローを保存し、Typeformでテストレスポンスを送信して、イベントがDifyに到着することを確認します。

## 接続モード

### 手動Webhook（コピー&ペースト）

1. Typeformフォームを開く → **Connect** → **Webhooks**。
2. Difyエンドポイント（ワークフローにこのトリガーを追加したときに表示される）を使用して新しいWebhookを追加します。
3. （推奨）「Secret」を有効にして、任意のランダムな文字列を貼り付けます。トリガーサブスクリプションの*Webhook Secret*フィールドに同じ値を記録して、プラグインが署名を検証できるようにします。
4. Webhookを有効にし、テストレスポンスを送信して`2xx`を受信することを確認します。

> Typeform APIを介してWebhookを管理する場合は、Webhookを作成または更新するときに`secret`フィールドを設定します。Dify内で同じ値を使用します。

### Personal Access Token経由の自動管理Webhook

1. Difyで、トリガーを設定するときに**Connect with API Key**を選択します。
2. `forms:read`、`webhooks:read`、および`webhooks:write`スコープを持つTypeform Personal Access Tokenを生成します（Account → Personal tokens）。
3. トークンをトリガー設定に貼り付けます。Difyはフォームをフェッチして動的ドロップダウンを表示します。
4. サブスクライブしたいフォームを選択します。オプションで、生成されたWebhookシークレットをオーバーライドできます。
5. DifyはTypeformでWebhookを作成（または更新）し、署名検証用のシークレットを保存します。

### OAuth 2.0経由の自動管理Webhook

1. [Typeform Developer Portal](https://developer.typeform.com/my-apps)でアプリケーションを作成し、`forms:read`、`webhooks:read`、`webhooks:write`、および`offline`スコープを有効にします。
2. トリガー設定でアプリのclient IDとclient secretを入力し、**Connect with OAuth**をクリックします。
3. Typeform同意フローを完了します。Difyはコードをトークンと交換します（そして、期限切れのアクセストークンを更新できるようにリフレッシュトークンを保持します）。
4. 動的ドロップダウンからターゲットフォームを選択し、オプションで生成されたシークレットをオーバーライドします。
5. DifyはOAuth認証情報を使用してTypeformでWebhookをプロビジョニングします。

### サブスクリプションパラメータ

| パラメータ | 使用時 | 説明 |
|-----------|-----------|-------------|
| `form_id` | 常にオプション | Webhookを手動で管理するときに単一のフォームにフィルタリングします。API Key / OAuthモードでは、このフィールドは動的ドロップダウンになり、必須になります。 |
| `webhook_secret` | 常にオプション | Webhookを手動で設定するときに`Typeform-Signature`ヘッダーを検証するために使用される共有シークレット。 |
| `webhook_secret`オーバーライド | API Key & OAuth | Webhookを自動作成する際に、Difyが生成するシークレットの代わりにカスタムシークレットを提供できます。 |

Difyがあなたの代わりにWebhookを作成するとき、生成された（またはオーバーライドされた）シークレットをサブスクリプションに保存するため、署名検証が自動的に機能します。

### イベントパラメータ

- `hidden_field_filter`: `form_response.hidden`と照合される`key=value`ペアのカンマ区切りリスト。
- `variable_filter`: `form_response.variables`のエントリと照合される`key=value`ペアのカンマ区切りリスト。

いずれかのフィルターが失敗すると、イベントは無視され、ワークフローはトリガーされません。

## サポートされているイベント

- `form_response_received` — すべてのTypeform Webhook配信（`event_type = "form_response"`）に対して発火されます。

### ペイロード形状

イベント出力スキーマは次を保証します：

```json
{
  "event_id": "LtWXD3crgy",
  "event_type": "form_response",
  "form_response": {
    "form_id": "lT4Z3j",
    "token": "a3a12ec67a1365927098a606107fac15",
    "...": "..."
  }
}
```

Typeformによって提供されるすべての追加フィールド（回答、定義、変数、非表示フィールドなど）は、ダウンストリーム使用のために保持されます。

## トラブルシューティング

- **OAuthサインインが失敗する**: リダイレクトURIがDifyに表示されているものと一致し、Typeformアプリが`forms:read`、`webhooks:read`、`webhooks:write`、および`offline`を付与していることを確認してください。
- **フォームドロップダウンが空**: アクセストークンには`forms:read`が含まれている必要があります；Personal Access Tokenを再生成するか、OAuth経由で再認可してください。
- **ワークフローがトリガーされない**: Typeform Webhookが「Enabled」を表示していること、Difyでトリガーがアクティブであること、および両側で同じWebhookシークレットが設定されていることを確認してください。
- **署名検証エラー**: Typeformでwebhookシークレットをローテーションし、新しい値をDifyに貼り付けます（手動モード）、または再接続してDifyに再生成させます（API Key / OAuth）。

## 参考資料

- [Typeform Webhooks APIドキュメント](https://www.typeform.com/developers/webhooks/)
- [Typeform Webhookセキュリティガイド](https://www.typeform.com/developers/webhooks/secure-your-webhooks/)
- [Typeform Personal Access Tokens](https://admin.typeform.com/account#/section/tokens)
- [Typeform OAuthスコープ](https://www.typeform.com/developers/webhooks/secure-your-webhooks/#oauth-scopes)
