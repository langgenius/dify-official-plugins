# Linear Trigger プラグイン

Linearの44のWebhookイベントトリガーをDifyワークフローに提供する包括的なプラグイン。Issues、コメント、プロジェクト、サイクル、ドキュメントなど、すべてのLinearイベントを監視して応答します。

## 機能

- **44のイベントタイプ**: すべてのLinear Webhookイベントを完全にカバー
- **デュアル認証**: APIキーとOAuth 2.0の両方をサポート
- **Webhook署名検証**: Linear Webhookリクエストを安全に検証
- **柔軟なフィルタリング**: 優先度、状態、名前、チームなどでイベントをフィルタリング
- **豊富なイベントデータ**: Linear Webhookペイロードから詳細情報を抽出

## バージョン

**現在のバージョン**: 0.3.0

## 利用可能なイベント（全44種類）

### Issue イベント (3)
- `issue_created`: 新しいIssueが作成された
- `issue_updated`: Issueが更新された
- `issue_removed`: Issueが削除またはアーカイブされた

### Comment イベント (3)
- `comment_created`: 新しいコメントが追加された
- `comment_updated`: コメントが編集された
- `comment_removed`: コメントが削除された

### Project イベント (3)
- `project_created`: 新しいプロジェクトが作成された
- `project_updated`: プロジェクトが更新された
- `project_removed`: プロジェクトが削除またはアーカイブされた

### Cycle イベント (3)
- `cycle_created`: 新しいサイクルが作成された
- `cycle_updated`: サイクルが更新された
- `cycle_removed`: サイクルが削除またはアーカイブされた

### Document イベント (3)
- `document_created`: 新しいドキュメントが作成された
- `document_updated`: ドキュメントが更新された
- `document_removed`: ドキュメントが削除またはアーカイブされた

### Attachment イベント (3)
- `attachment_created`: 新しい添付ファイルが追加された
- `attachment_updated`: 添付ファイルが更新された
- `attachment_removed`: 添付ファイルが削除された

### IssueLabel イベント (3)
- `issue_label_created`: 新しいラベルが作成された
- `issue_label_updated`: ラベルが更新された
- `issue_label_removed`: ラベルが削除された

### Reaction イベント (3)
- `reaction_created`: 新しいリアクションが追加された
- `reaction_updated`: リアクションが更新された
- `reaction_removed`: リアクションが削除された

### ProjectUpdate イベント (3)
- `project_update_created`: 新しいプロジェクト更新が投稿された
- `project_update_updated`: プロジェクト更新が編集された
- `project_update_removed`: プロジェクト更新が削除された

### Initiative イベント (3)
- `initiative_created`: 新しいイニシアチブが作成された
- `initiative_updated`: イニシアチブが更新された
- `initiative_removed`: イニシアチブが削除された

### InitiativeUpdate イベント (3)
- `initiative_update_created`: 新しいイニシアチブ更新が投稿された
- `initiative_update_updated`: イニシアチブ更新が編集された
- `initiative_update_removed`: イニシアチブ更新が削除された

### Customer イベント (3)
- `customer_created`: 新しい顧客が作成された
- `customer_updated`: 顧客が更新された
- `customer_removed`: 顧客が削除された

### CustomerNeed イベント (3)
- `customer_need_created`: 新しい顧客ニーズが作成された
- `customer_need_updated`: 顧客ニーズが更新された
- `customer_need_removed`: 顧客ニーズが削除された

### User イベント (2)
- `user_created`: 新しいユーザーが追加された
- `user_updated`: ユーザーが更新された

### IssueRelation イベント (3)
- `issue_relation_created`: 新しいIssue関連が作成された
- `issue_relation_updated`: Issue関連が更新された
- `issue_relation_removed`: Issue関連が削除された

## クイックスタート
### 1. 認証とサブスクリプションオプション

このプラグインは、Linear Webhookサブスクリプションと認証のための**3つのモード**をサポートしています。ユースケースに最適なオプションを選択してください：

#### オプション1: OAuth 2.0（推奨）

**デフォルトOAuthクライアント（Dify Cloud）**
- Dify Cloudでは、Linearはワンクリック認証用のデフォルトOAuthクライアントで事前設定されています。
- **Create with OAuth > Default**を選択し、LinearでDifyを即座に認可します。

**カスタムOAuthクライアント（セルフホスト）**
- セルフホスト環境では、独自のOAuthアプリケーションを作成する必要があります。
- **Create with OAuth > Custom**を選択します。
- [Linear Settings > API Applications](https://linear.app/settings/api/applications)にアクセスし、新しいOAuthアプリケーションを作成します。
- LinearでOAuthアプリケーションを作成するときに、Difyが提供するコールバックURLを使用します。
- Difyに戻り、Linear OAuthアプリケーションからのClient IDとClient Secretを入力し、**Save and Authorize**をクリックします。
- 保存すると、同じクライアント認証情報を将来のサブスクリプションで再利用できます。
- サブスクリプション名を指定し、サブスクライブするイベントを選択し、その他の必要な設定を構成します。
- 利用可能なすべてのイベントを選択することをお勧めします。
- **Create**をクリックします。

サブスクリプション設定ページに表示されるCallback URLは、Difyが代わりにLinearでWebhookを作成するために内部的に使用されます。このURLに対してアクションを取る必要はありません。

#### オプション2: APIキー認証

- **Create with API Key**を選択します。
- [Linear Settings > API](https://linear.app/settings/api)にアクセスし、Personal API Keyを作成します。
- DifyにAPI Keyを入力し、**Verify**をクリックします。
- サブスクリプション名を指定し、サブスクライブするイベントを選択し、その他の必要な設定を構成します。
- 利用可能なすべてのイベントを選択することをお勧めします。
- **Create**をクリックします。

#### オプション3: 手動Webhookセットアップ

- **Paste URL**を選択して新しいサブスクリプションを作成します。
- サブスクリプション名を指定し、提供されたコールバックURLを使用してLinearでWebhookを手動で作成します。
- Linear Workspace Settings > Webhooksに移動し、DifyコールバックURLを指すWebhookを新しく作成します。
- （オプション）リクエスト署名検証のためにLinearでWebhookシークレットを追加します。
- （オプション）作成したWebhookをテストします：
  - Linearは作成時にDifyにpingリクエストを送信して、新しいWebhookを自動的にテストします。
  - サブスクライブしたイベントをトリガーして、LinearがコールバックURLにHTTPリクエストを送信するようにすることもできます。
  - Manual SetupページのRequest Logsセクションを確認します。Webhookが正常に機能している場合、受信したリクエストとDifyの応答が表示されます。
- **Create**をクリックします。

**注意：**
- 最高のセキュリティとチーム管理には、OAuth 2.0が推奨されます。
- Webhook Secret（Linearではオプション）は、追加のセキュリティのためにリクエスト署名検証を有効にします。

どのオプションがニーズに合うか不明な場合は、Difyのプラグイン設定ページまたはLinearドキュメントを参照して、ステップバイステップのガイダンスをご覧ください。

## イベントパラメータ

各イベントは、ノイズを減らすための特定のフィルターパラメータをサポートしています：

### 共通フィルター

- **title_contains/name_contains/body_contains**: キーワードフィルター（カンマ区切り）
- **priority_filter**: 優先度レベルでフィルタリング（0-4）
- **state_filter**: ワークフロー状態でフィルタリング
- **team_filter**: チームIDでフィルタリング
- **email_contains**: メールパターンでフィルタリング
- **emoji_filter**: 特定の絵文字でフィルタリング
- **issue_only**: Issue関連アイテムのみトリガー
- **project_only**: プロジェクト関連アイテムのみトリガー
- **status_changed**: ステータス変更時のみトリガー

## サポート

参考: [Linear Webhooksドキュメント](https://linear.app/developers/webhooks)
