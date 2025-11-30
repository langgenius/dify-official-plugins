Gmail Trigger（Push + History）

概要

- Gmail Triggerは、Cloud Pub/Sub経由でGmailプッシュ通知を受信し、Gmail Historyに基づいて具体的なイベントを発行するDifyプロバイダーです：
  - `gmail_message_added`（新しいメッセージ）
  - `gmail_message_deleted`（削除されたメッセージ）
  - `gmail_label_added`（メッセージにラベルが追加された）
  - `gmail_label_removed`（メッセージからラベルが削除された）
- ディスパッチはプッシュを検証/認証し、履歴デルタを一度プルし、イベントが使用するために変更を分割します。
- 注意：Gmail APIアクセスにはAPIキーはサポートされていません。OAuth（gmail.readonly）のみを使用してください。

前提条件

- Gmail APIの認可を受けたGoogleアカウント（OAuth中に使用）
- Pub/Sub APIが有効化されたGoogle Cloudプロジェクト（管理者がテナントレベルで設定）

セットアップ手順

1. Difyにプラグインをインストール

- オプション：
  - `.difypkg` としてパッケージ化されている場合、DifyのPlugin Centerでインポート（Plugins → Import）。
  - 開発中のローカル実行の場合、ランタイムが `requirements.txt` の依存関係をインストールすることを確認してください。

2. GCPリソースの設定（管理者、一度だけのセットアップ）

- Pub/SubリソースをホストするGoogle Cloudプロジェクトを作成または選択します。以下のAPIが有効になっていることを確認してください _（APIs & Services → Library）_：
  - Gmail API: https://console.cloud.google.com/apis/library/gmail.googleapis.com
  - Cloud Pub/Sub API: https://console.cloud.google.com/apis/library/pubsub.googleapis.com
- 専用のサービスアカウントを作成し、Pub/Sub権限を付与します：

  1. IAM & Admin → Service Accounts → **Create Service Account** に移動します。  
     Console URL: https://console.cloud.google.com/iam-admin/serviceaccounts

     スクリーンショット：

     [![GCP Service Account](./_assets/GCP_SERVICE_ACCOUNT.png)](./_assets/GCP_SERVICE_ACCOUNT.png)

  2. このサービスアカウントに `roles/pubsub.admin` ロールを割り当てるか、「Pub/Sub Admin」ロールを選択します。これには必要な権限がすでに含まれています（プラグインがトピック、サブスクリプションを作成し、IAMポリシーを自動的に更新できるようにするために必要）。

     - または、カスタムロールには次のものが含まれている必要があります：`pubsub.topics.create`、`pubsub.topics.getIamPolicy`、`pubsub.topics.setIamPolicy`、`pubsub.subscriptions.create`、`pubsub.subscriptions.get`、`pubsub.subscriptions.delete`、`pubsub.subscriptions.list`。

       スクリーンショット：

       [![GCP Permissions](./_assets/GCP_PERMISSION.png)](./_assets/GCP_PERMISSION.png)

  3. このサービスアカウント用のJSONキーを作成し、安全にダウンロードします。
     スクリーンショット：

     [![GCP Key](./_assets/GCP_KEY.png)](./_assets/GCP_KEY.png)

- Google Cloudの**Project ID**をメモしてください（プロジェクトダッシュボードまたはIAMページに表示されます）。

3. プラグイン用のOAuthクライアントを設定（管理者、一度だけのセットアップ）

- Google Cloud Console → APIs & Services → Credentials → **Create Credentials** → OAuth client ID。  
  Console URL: https://console.cloud.google.com/apis/credentials

  スクリーンショット：

  [![GCP OAuth Client](./_assets/GC_OAUTH_CLIENT.png)](./_assets/GC_OAUTH_CLIENT.png)

  - Application type: **Web application**
  - Authorized redirect URIs: プラグインをセットアップするときにDifyに表示されるリダイレクトURIをコピーします（例：`https://<your-dify-host>/console/api/plugin/oauth/callback`）

- 生成された**Client ID**と**Client Secret**を後で使用するために取得します。

4. DifyにOAuthクライアントパラメータを入力

- プラグイン設定フォームで：
  - `client_id`: 上記で作成したOAuthクライアントID。
  - `client_secret`: 対応するクライアントシークレット。
  - `gcp_project_id`: Pub/Subが有効になっているGoogle CloudプロジェクトID。
  - `gcp_service_account_json`: サービスアカウント用に作成された完全なJSONキーを貼り付けます（プライベートに保ってください）。
- エンドユーザーがプラグインを認可すると、Difyは自動的にユーザーごとのPub/Subトピックを導出します。

5. ユーザー：認可とサブスクリプションの作成

- 「Authorize」をクリックしてOAuthを完了します（gmail.readonlyスコープ）
- オプションのパラメータを使用してGmailサブスクリプションを作成します：
  - `label_ids`（オプション）：特定のラベル（INBOX、UNREADなど）にスコープを設定
    - ドキュメント：https://developers.google.com/gmail/api/reference/rest/v1/users.labels/list
  - Properties（オプション、セキュリティ強化のため）：
    - `require_oidc`: OIDCベアラー検証を強制
    - `oidc_audience`: Webhookエンドポイント URL（自動入力）
    - `oidc_service_account_email`: Pushサブスクリプションに使用されるサービスアカウント

自動的に行われること：

- プラグインはGCPプロジェクトでPub/Subトピックを作成/再利用します
- プラグインはトピックにGmail APIパブリッシャー権限を付与します
- プラグインはこのユーザー専用のPushサブスクリプションを作成します
- プラグインはGmail `users.watch` APIを呼び出して監視を開始します
- サブスクリプション解除時、プラグインはPushサブスクリプションをクリーンアップします（トピックは再利用のために保持されます）

OIDC値の取得場所

- `oidc_audience`
  - Difyサブスクリプション詳細（Endpoint）に表示される正確なWebhookエンドポイントURLを使用します。例：
    - `https://<your-dify-host>/triggers/plugin/<subscription-id>`
  - YAMLフィールドには、`audience` クレームに関するGoogleドキュメントへのURLが含まれています：OIDCトークンリファレンスを参照してください。
- `oidc_service_account_email`
  - Pub/Subプッシュサブスクリプションで使用されるサービスアカウント（`--push-auth-service-account` 経由で設定）。
  - Google Cloud Console → IAM & Admin → Service Accountsで見つけるか、次のコマンドで確認できます：
    - `gcloud iam service-accounts list --format='value(email)'`
  - YAMLフィールドには、Service Accountsコンソールページへのリンクがあります。

仕組み

- ディスパッチ（トリガー）
  - オプションでPub/SubプッシュからのOIDCベアラーを検証（iss/aud/email）
  - `message.data` をデコードして `historyId`/`emailAddress` を取得
  - `users.history.list(startHistoryId=...)` を一度呼び出してデルタを収集
  - ファミリーごとに変更を分割し、保留中のバッチをDifyストレージに保存
  - Difyが実行する具体的なイベント名のリストを返します
- イベント
  - ファミリーの保留中のバッチを読み取ります
  - `gmail_message_added` は完全なメッセージメタデータ（ヘッダー、添付ファイルメタ）をフェッチします
  - 出力はイベントYAML `output_schema` と一致します

イベント出力（概要）

- `gmail_message_added`
  - `history_id`: string
  - `messages[]`: id, threadId, internalDate, snippet, sizeEstimate, labelIds, headers{From,To,Subject,Date,Message-Id}, has_attachments, attachments[]
- `gmail_message_deleted`
  - `history_id`: string
  - `messages[]`: id, threadId
- `gmail_label_added` / `gmail_label_removed`
  - `history_id`: string
  - `changes[]`: id, threadId, labelIds

添付ファイルの処理

- トリガーは、最大20個の実際の添付ファイル（`attachmentId` またはインラインコンテンツを持つ）をアップロードしようとし、5 MiBを超える個別のファイルはスキップします。
- `attachments[].file_url` は唯一の外部公開ダウンロードアドレスです；`attachments[].file_source` はその起源を識別します（元のリンクの場合は `gmail`、Difyミラーの場合は `dify_storage`）。
- 添付ファイルがDifyに正常にアップロードされると、`upload_file_id` と `original_url`（Gmail/Drive元のアドレス）の両方が返されます；ミラーリングされていない場合、`original_url` は省略されます。
- Gmailは、サイズの大きい添付ファイルに対してDriveリンクを返すことが多く、またはメッセージ本文に直接共有アドレスを提供します。イベントはテキスト/HTMLコンテンツをスキャンしてこれらのリンクを抽出し、呼び出し元による統一処理のために添付ファイルアイテムとして返します。
- 呼び出し元は `file_url` のみを使用すればよく、`file_source` に基づいてGmail/Driveに直接アクセスするか、Difyストレージを経由するかを判断します。

ライフサイクルと更新

- 作成：プラグインはPub/Subを自動プロビジョニングし、その後 `topicName` とオプションの `labelIds` で `users.watch` を呼び出します
- 更新：有効期限前に `users.watch` が再度呼び出されます（Gmailのwatchは時間制限があり、約7日間）
- 削除：`users.stop` を呼び出し、Pushサブスクリプションをクリーンアップします

テスト

- 監視対象のメールボックス（INBOX）にメールを送信します。`gmail_message_added` が表示されるはずです
- 既読/未読をマーク（UNREADラベルが削除/追加される）すると、ラベルイベントがトリガーされます
- メールを削除すると `gmail_message_deleted` がトリガーされます
- ヒント：Pub/Subサブスクリプションの詳細で最近の配信を表示できます；Difyのログ/コンソールにトリガーとイベントのトレースが表示されます。

トラブルシューティング

- プラグインがサブスクリプションの作成に失敗する：OAuthクライアントパラメータでGCPクレデンシャルが正しく設定されていることを確認してください
- 何もトリガーされない：Gmail APIとPub/Sub APIがGCPプロジェクトで有効になっていることを確認してください
- ディスパッチ時の401/403：OIDC設定の不一致；サービスアカウントとオーディエンスを確認してください
- `historyId` が古い：プラグインはチェックポイントを最新の通知にリセットし、バッチをスキップします
- OAuthの問題：再認可；gmail.readonlyスコープが付与されていることを確認してください

参考資料

- Gmail Push: https://developers.google.com/workspace/gmail/api/guides/push
- History: https://developers.google.com/gmail/api/reference/rest/v1/users.history/list
- Messages: https://developers.google.com/gmail/api/reference/rest/v1/users.messages/get
