# Notion Trigger プラグイン

このプラグインは、Notion Webhookをサブスクライブすることで、ページ、データベース、データソース、コメントの更新など、リアルタイムのNotionアクティビティにDifyを反応させることができます。Notionワークスペースでイベントが発生すると、Notionは設定されたDifyエンドポイントにイベントペイロードを安全にPOSTします。プラグインはイベントデータをDifyトリガー変数にマッピングするため、ポーリングなしで自動化を構築したり、変更を即座に処理したりできます。

Notion WebhookとサポートされているイベントタイプについてDetail: [Notion APIドキュメント](https://developers.notion.com/reference/webhooks)をご覧ください。

## Webhookサブスクリプションの設定

1. Notionで、統合設定 → Webhooks → サブスクリプションを作成を開きます。
2. DifyによってProvideされたトリガーエンドポイントをWebhook URLとして貼り付けます。
3. Notionに発行させたいイベントタイプを選択します。（このリストは後で変更できます。）
4. フォームを送信します。Notionは直ちに `{"verification_token": "..."}` のみを含むJSONペイロードをPOSTします。
5. Difyで、このプラグインの新しいトリガー接続を作成し、`verification_token` 値をVerification Tokenフィールドに貼り付けます。オプションで、Event Filtersチェックボックスリストで同じイベントタイプを選択して、ワークフローにサブセットのみを転送できます。
6. Notionに戻り、Verifyをクリックします。検証が成功すると、NotionはDifyへの完全なWebhookイベントの配信を開始します。

### ワークスペースフィルタリング

すべてのイベント定義には、オプションの `workspace_filter` パラメータが含まれています。ワークスペースIDのカンマ区切りリストを提供して、これらのワークスペースのみにトリガーを制限します。フィールドを空のままにすると、サブスクリプションに関連付けられた任意のワークスペースからのイベントを受け入れます。

## サポートされているイベント

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

### Data Source (APIバージョン 2025-09-03)
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
