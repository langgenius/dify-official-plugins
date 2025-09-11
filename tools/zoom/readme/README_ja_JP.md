# Dify Zoom プラグイン

**作成者**: langgenius  
**バージョン**: 0.1.0  
**タイプ**: tool

## 概要

このプラグインはZoomビデオ会議プラットフォームと統合し、包括的な会議管理機能を提供します。Difyプラットフォームを通じてZoom会議の自動作成、取得、更新、削除を可能にします。このプラグインは、インスタント、スケジュール済み、定期開催会議など、さまざまな会議タイプをサポートし、高度な設定オプションを提供します。

## セットアップ

1. [Zoom App Marketplace](https://marketplace.zoom.us/develop/create)でアプリケーションを作成します。

   <img src="_assets/create_app.png" alt="Create App" width="300"/>

   *新しいZoomアプリケーションを作成*

2. アプリタイプとして**General App**を選択します。

3. アプリケーションを以下のように設定します：
    - **App name**: Dify Zoom Plugin
    - **Choose your app type**: Server-to-Server OAuth
    - **Would you like to publish this app on Zoom App Marketplace?**: No (プライベート使用)

4. **OAuth**セクションで：
    - **OAuth Redirect URL**: 適切なリダイレクトURIを設定：
        - SaaS (cloud.dify.ai) ユーザーの場合：`https://cloud.dify.ai/console/api/oauth/plugin/langgenius/zoom/zoom/tool/callback`
        - セルフホストユーザーの場合：`http://<YOUR_LOCALHOST_CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/zoom/zoom/tool/callback`
    - **OAuth allow list**: 必要に応じてドメインを追加

5. App Credentialsセクションから**Client ID**と**Client Secret**をコピーします。

6. 以下のようにスコープを選択：

   <img src="_assets/add_scope.png" alt="Add Scope" width="300"/>

   *OAuth許可スコープを設定*

7. テストユーザーを追加：

   <img src="_assets/add_test_user.png" alt="Add Test User" width="300"/>

   *アプリケーションにテストユーザーを追加*

8. Difyでプラグインを設定：
    - Zoomアプリからコピーした値で**Client ID**と**Client Secret**フィールドを入力
    - リダイレクトURIがZoom App Marketplaceで設定したものと一致することを確認
    - `Save and authorize`をクリックしてOAuthフローを開始し、権限を付与

9. Zoomアカウントにログインしてアプリの権限を承認し、OAuth認証プロセスを完了します。

## 使用デモ

<img src="_assets/result.png" alt="Plugin Result" width="300"/>

*プラグインの統合と使用デモンストレーション*

## ツールの説明

### zoom_create_meeting
カスタマイズ可能な設定で新しいZoom会議を作成し、会議リンクを取得します。

**パラメータ：**
- **topic** (string, 必須): 会議のトピックまたはタイトル
- **type** (select, オプション): 会議タイプ - インスタント (1)、スケジュール済み (2)、固定時間なし定期 (3)、または固定時間あり定期 (8)。デフォルト：スケジュール済み (2)
- **start_time** (string, オプション): ISO 8601形式の会議開始時間（例：2024-12-25T10:00:00Z）
- **duration** (number, オプション): 会議の長さ（分）（1-1440）。デフォルト：60
- **password** (string, オプション): 会議を保護するためのオプションパスワード
- **waiting_room** (boolean, オプション): 参加者の待機室を有効化。デフォルト：true
- **join_before_host** (boolean, オプション): ホストの到着前に参加者の参加を許可。デフォルト：false
- **mute_upon_entry** (boolean, オプション): 参加時に参加者を自動ミュート。デフォルト：true
- **auto_recording** (select, オプション): 自動録画設定 - なし、ローカル、またはクラウド。デフォルト：なし
- **timezone** (string, オプション): 会議のタイムゾーン。デフォルト：UTC
- **agenda** (string, オプション): 会議のアジェンダまたは詳細な説明

**戻り値：** 会議ID、参加URL、開始URL、パスワード、会議詳細。

### zoom_get_meeting
会議IDでZoom会議の包括的な情報を取得します。

**パラメータ：**
- **meeting_id** (string, 必須): Zoom会議の一意識別子
- **occurrence_id** (string, オプション): 定期会議のオカレンスID
- **show_previous_occurrences** (boolean, オプション): 定期会議の過去のオカレンスを含める。デフォルト：false

**戻り値：** 設定、URL、ホスト詳細、定期会議のオカレンスデータを含む完全な会議情報。

### zoom_list_meetings
認証されたユーザーのすべてのZoom会議を高度なフィルタリングオプション付きで一覧表示します。

**パラメータ：**
- **type** (select, オプション): 会議タイプフィルタ - スケジュール済み、ライブ、今後、今後の会議、または過去の会議。デフォルト：スケジュール済み
- **page_size** (number, オプション): ページあたりの会議数（1-300）。デフォルト：30
- **page_number** (number, オプション): 取得するページ番号（1から開始）。デフォルト：1
- **from_date** (string, オプション): 会議フィルタリングの開始日（YYYY-MM-DD形式）
- **to_date** (string, オプション): 会議フィルタリングの終了日（YYYY-MM-DD形式）

**戻り値：** ページネーション情報と適用されたフィルタ付きの会議リスト。

### zoom_update_meeting
既存のZoom会議を新しい設定と構成で更新します。

**パラメータ：**
- **meeting_id** (string, 必須): 更新するZoom会議の一意識別子
- **topic** (string, オプション): 新しい会議トピックまたはタイトル
- **type** (select, オプション): 新しい会議タイプ
- **start_time** (string, オプション): ISO 8601形式の新しい開始時間
- **duration** (number, オプション): 新しい長さ（分）（1-1440）
- **timezone** (string, オプション): 新しいタイムゾーン識別子
- **password** (string, オプション): 新しい会議パスワード
- **agenda** (string, オプション): 新しい会議アジェンダまたは説明
- **waiting_room** (boolean, オプション): 待機室設定を更新
- **join_before_host** (boolean, オプション): ホスト前参加設定を更新
- **mute_upon_entry** (boolean, オプション): 参加時ミュート設定を更新
- **auto_recording** (select, オプション): 新しい自動録画設定
- **occurrence_id** (string, オプション): 定期会議の特定のオカレンスを更新するためのオカレンスID

**戻り値：** 成功ステータス、更新された会議情報、変更の詳細。

### zoom_delete_meeting
通知オプション付きで会議IDによりZoom会議を削除します。

**パラメータ：**
- **meeting_id** (string, 必須): 削除するZoom会議の一意識別子
- **occurrence_id** (string, オプション): 定期会議の特定のオカレンスを削除するためのオカレンスID
- **schedule_for_reminder** (boolean, オプション): キャンセルについて登録者にリマインダーメールを送信。デフォルト：false
- **cancel_meeting_reminder** (boolean, オプション): 登録者とパネリストにキャンセルメールを送信。デフォルト：false

**戻り値：** 成功ステータス、削除された会議情報、削除タイプ（会議全体または特定のオカレンス）。

## プライバシー

このプラグインを使用する際のデータ処理方法については、[プライバシーポリシー](PRIVACY.md)をご参照ください。

最終更新：2025年8月