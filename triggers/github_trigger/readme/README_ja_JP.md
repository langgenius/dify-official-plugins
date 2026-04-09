GitHub Trigger（Webhooks）

概要

- GitHub Triggerは、リポジトリのWebhookをDifyに接続し、Issues、プルリクエスト、CI/CDジョブ、セキュリティアラートなどの具体的なイベントを配信します。
- サブスクリプションは自動的にプロビジョニングできます：プラグインが選択したリポジトリにWebhookを作成し、シークレットを生成して署名検証用に保存します。
- OAuth（推奨）と個人アクセストークンの両方がサポートされているため、管理者はユーザーごとの認可フローと共有GitHubクレデンシャルのいずれかを選択できます。
- 受信ペイロードは、Difyがトリガーイベントを受信する前に検証されます（`X-Hub-Signature-256`、`X-GitHub-Event`）。

前提条件

- イベントを発行する各リポジトリに対する管理者権限を持つGitHubユーザー。
- GitHubがHTTPS経由でアクセスできるDifyインスタンス（Webhook配信用の公開アクセス可能なエンドポイント）。
- 以下のいずれかのクレデンシャルオプション：
  - GitHub OAuth App（クライアントID/シークレット、スコープ `read:user admin:repo_hook`）。
  - リポジトリ管理権限を持つGitHub fine-grained個人アクセストークン → **Repository hooks: Read & Write**。

セットアップ手順

1. Difyにプラグインをインストール

- オプション：
  - Plugin Centerで `.difypkg` をインポート（Plugins → Import）。
  - 開発中は、ランタイムが `requirements.txt` から依存関係をインストールすることを確認してください。

2. 認証戦略を選択（管理者）

- **OAuth（推奨）**：ユーザーは自分のGitHub IDで認可し、Difyは更新可能なアクセストークンのみを保存します。
- **個人アクセストークン**：管理者がWebhook管理権限を付与するPATを貼り付けます；すべてのサブスクリプションが同じトークンを共有します。

3. （OAuthのみ）GitHub OAuth Appを作成

- GitHub Settings → Developer settings → OAuth Apps → **New OAuth App**  
  URL: https://github.com/settings/applications/new
  ![GitHub OAuth App](_assets/GITHUB_OAUTH_APP.png)

- 設定：
  - Application name: わかりやすい名前（例：「Dify GitHub Trigger」）
  - Homepage URL: DifyコンソールのURL
  - Authorization callback URL: `https://<your-dify-host>/console/api/plugin/oauth/callback`
- 生成された**Client ID**と**Client Secret**を取得します。
- 必要に応じてスコープを調整します；プラグインのデフォルトは `read:user admin:repo_hook` で、リポジトリ全体へのアクセスなしでWebhook管理を可能にします。

4. Difyにクレデンシャルを入力（管理者）

- OAuthの場合：
  - `client_id`: OAuth Appから。
  - `client_secret`: OAuth Appから。
  - `scope`（オプション）：追加のGitHub APIが必要でない限り、デフォルトのままにします。
- 個人アクセストークンの場合：
  - `access_tokens`: PATを貼り付けます；上記のリポジトリフック権限があることを確認してください。

5. ユーザー：サブスクリプションを作成

- **Authorize**をクリック（OAuth）するか、PATが設定されていることを確認します；プラグインは認証されたアカウントが管理できるリポジトリを取得します。
- ドロップダウンからターゲット `repository` を選択します（形式 `owner/repo`）。
- 1つ以上のWebhook `events` を選択します。デフォルトはほとんどのリポジトリレベルのアクティビティをカバーしています；ノイズを減らすためにリストを絞り込むことができます。
- （オプション）Webhookを手動で管理する場合は `webhook_secret` を提供します。DifyがWebhookをプロビジョニングする場合、シークレットは自動的に生成され、サブスクリプションと共に保存されます。
- 手動Webhookセットアップ：GitHub → Repository Settings → Webhooksで、**Content type**を `application/json` に設定します。トリガーは生のJSONペイロード（`Content-Type: application/json`）のみを受け入れ、`application/x-www-form-urlencoded` は拒否します。
- サブスクリプションを保存します。Difyは手動セットアップまたは診断用にWebhookエンドポイントURL（`https://<dify-host>/triggers/plugin/<subscription-id>`）を表示します。
    ![GitHub Webhook](_assets/GITHUB_WEBHOOK.png)

自動的に行われること

- プラグインはGitHubの `repos/{owner}/{repo}/hooks` APIを呼び出してWebhookを作成（または後で削除）し、`content_type=json` と共有シークレットを含むJSONペイロードを使用します。
- Webhookシークレットは、提供されていない場合、UUID4の16進文字列で生成され、すべての配信でHMAC SHA-256署名検証（`X-Hub-Signature-256`）を可能にします。
- サブスクリプションの更新により、WebhookのTTL（約30日）が延長され、GitHubは再認可なしでアクティブに保ちます。
- サブスクリプション解除時、Webhookは `DELETE repos/{owner}/{repo}/hooks/{hook_id}` を介して削除されます。

サポートされているイベント（概要）

- `issues`、`issue_comment`、`pull_request`、および関連するレビュー/コメントイベント。
- CI/CDと自動化：`check_run`、`check_suite`、`workflow_run`、`workflow_job`、`deployment`、`deployment_status`。
- リポジトリアクティビティ：`push`、`ref_change`（作成/削除）、`commit_comment`、`star`、`watch`、`fork`、`public`、`repository`。
- プロジェクトとコラボレーション：`project`、`project_card`、`project_column`、`discussion`、`discussion_comment`、`label`、`milestone`、`member`。
- セキュリティと品質：`code_scanning_alert`、`dependabot_alert`、`repository_vulnerability_alert`、`secret_scanning`。
- 設定とガバナンス：`branch_protection_configuration`、`branch_protection_rule`、`repository_ruleset`、`custom_property_values`。

仕組み

- ディスパッチ
  - シークレットが存在する場合、Webhook署名を検証します。
  - JSON（またはフォームエンコードされたリクエストの `payload`）を解析し、`X-GitHub-Event` を取得します。
  - GitHubイベントを具体的なDifyイベント名にマッピングします（例：`deployment_status` → `deployment_status_created`、`create/delete` → `ref_change`）。
  - GitHubが配信を成功とみなすように、JSON `{"status": "ok"}` レスポンスを返します。
- イベント
  - 各イベントYAMLは保存されたペイロードを読み込み、最も関連性の高いフィールドを強調表示し、ダウンストリームワークフローの構造化された出力として公開します。
  - アクションベースのイベント（例：リリース公開）は、自動化を明確かつ決定論的に保つために分割されます。


トラブルシューティング

- Webhook作成が失敗する：OAuthトークンまたはPATに `admin:repo_hook` スコープがあり、アクターがリポジトリの管理者であることを確認してください。
- 「Webhook署名がありません」：サブスクリプションフォームでシークレットを提供する（手動Webhookの場合）か、DifyにWebhookを再作成させます。
- イベントが到着しない：Difyエンドポイントが公開アクセス可能（ステータス200）であり、選択したイベントが期待するGitHubアクティビティと一致していることを確認してください。
- 401/403レスポンス：プラグインを再認可します；失効したトークンまたは期限切れのPATは交換する必要があります。

参考資料

- GitHub Webhooks: https://docs.github.com/webhooks
- OAuth Apps: https://docs.github.com/apps/oauth-apps
- Event payloads: https://docs.github.com/webhooks-and-events/webhooks/webhook-events-and-payloads
