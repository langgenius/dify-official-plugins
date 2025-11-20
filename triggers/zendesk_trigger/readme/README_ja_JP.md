# Dify用Zendesk Triggerプラグイン

Zendeskのカスタマーサービスプラットフォームとdifyのai能力をWebhookトリガーを介して接続する包括的なプラグイン。

## 概要

このプラグインは、Webhookトリガーを介してZendeskのカスタマーサービスプラットフォームとDifyのAI機能を接続します。さまざまなZendeskイベントをサポートして、インテリジェントなカスタマーサービス自動化とナレッジベース最適化を可能にします。

## ユースケース

### 1. インテリジェントチケット処理
- **シナリオ**: 新しいチケットを自動的に分析し、適切なエージェントにルーティング
- **トリガー**: `ticket_created`
- **ワークフロー**:
  - AIがチケットの内容、優先度、センチメントを分析
  - 専門知識に基づいて最適なエージェントを推奨
  - 初期応答の提案を生成

### 2. SLAモニタリングとアラート
- **シナリオ**: プロアクティブアラートでSLA違反を防止
- **トリガー**: `ticket_status_changed`、`ticket_priority_changed`
- **ワークフロー**:
  - チケットのステータス遷移を監視
  - SLA期限に近づいたときにアラート
  - 自動エスカレーションをトリガー

### 3. ナレッジベース最適化
- **シナリオ**: チケットのトレンドに基づいてヘルプセンターコンテンツを改善
- **トリガー**: `article_published`、`article_unpublished`
- **ワークフロー**:
  - 一般的なチケットトピックを分析
  - ナレッジベース記事を推奨
  - エージェントの効率を最適化

## サポートされているイベント

### チケットイベント
- **ticket_created**: 新しいサポートチケットが作成された
- **ticket_marked_as_spam**: Zendeskによってチケットがスパムとしてフラグされた
- **ticket_status_changed**: チケットのステータスが変更された（new → open → solved → closed）
- **ticket_priority_changed**: チケットの優先度が変更された（low → urgent）
- **ticket_comment_created**: チケットにコメントが追加された（公開または非公開）

### ナレッジベースイベント
- **article_published**: ヘルプセンター記事が公開された
- **article_unpublished**: ヘルプセンター記事が非公開になった

## 設定

### 前提条件
1. 管理者アクセス権を持つZendeskアカウント
2. Zendesk Admin CenterからのAPIトークンまたはOauthクライアント
3. Zendeskサブドメイン（例：acme.zendesk.comの場合は`acme`）

### セットアップ手順

1. **APIトークン設定**

![1](./_assets/1.png)

- `Apps and integrations/Apis/Api tokens`に移動
- APIトークンを追加
- apiをdifyに設定

![2](./_assets/2.png)

2. **Oauthクライアント設定**

![3](./_assets/3.png)
![4](./_assets/4.png)

- oauthクライアント設定はより複雑なので、2つのスクリーンショットを比較しましょう
- difyの`Client ID`はZendeskの`Identifier`です
- ZendeskのRedirect URLsはdifyからコピーする必要があります
- Zendeskの`Client kind`は`Confidential`を選択する必要があります

## バージョン履歴

- **1.0.0** (2025-10-31): 初回リリース
  - チケット、コメント、記事イベントのサポート
  - 包括的なフィルタリングオプション
  - Webhook署名検証
  - 多言語サポート（EN、ZH、JA）
