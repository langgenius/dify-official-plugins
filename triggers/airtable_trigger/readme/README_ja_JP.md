# Dify用Airtable Triggerプラグイン

## 概要

このプラグインは、ベース内のレコードが作成、更新、または削除されたときに、AirtableからリアルタイムのWebhook通知をDifyが受信できるようにします。AirtableとDifyワークフロー間のシームレスな統合を提供します。


## Airtable Personal Access Tokenの取得

![1](./_assets/1.png)
1. [Airtable Account Settings](https://airtable.com/create/tokens)にアクセス
2. 「Create new token」をクリック
3. トークンに名前を付けます（例：「Dify Integration」）
4. 以下のスコープを追加:
   - `webhook:manage`
   - `data.records:read`
   - `schema.bases:read`
5. 監視したい特定のベースへのアクセスを追加
6. 「Create token」をクリックしてトークン値をコピー

## 設定

### 設定項目

- **Personal Access Token**: Airtable Personal Access Token
- **Base ID**: 監視するAirtableベースのID（ベースURLに記載: `https://airtable.com/{baseId}/...`）
- **Events**: 監視するイベントタイプを選択（作成、更新、削除）
- **Table IDs**: 監視する特定のテーブルIDのカンマ区切りリスト（すべてのテーブルを監視する場合は空のままにします）

## 使用例

1. DifyワークスペースにAirtable Triggerプラグインをインストール
2. 新しいワークフローを作成し、Airtable Triggerを追加
3. Personal Access TokenとBase IDでトリガーを設定
4. 監視したいイベントを選択
5. オプションのフィルターを追加して通知を絞り込む
6. ワークフローを保存してアクティブ化

## 出力変数

トリガーはワークフローに以下の変数を提供します：

```json
{
  "base_id": "appXXXXXXXXXXXXXX",
  "webhook_id": "achXXXXXXXXXXXXXX",
  "timestamp": "2023-01-01T00:00:00.000Z",
  "cursor": 9,
  "payloads": { /* 完全なWebhook通知ペイロード */ }
}
```

## 参考資料

- [Airtable Webhooks APIドキュメント](https://airtable.com/developers/web/api/webhooks-overview)
- [Airtable認証](https://airtable.com/developers/web/api/authentication)
- [Airtableスコープ](https://airtable.com/developers/web/api/scopes)
