# Google Drive Trigger プラグインユーザーガイド

## このプラグインの機能

- Google Driveがファイルまたはドライブの変更を通知すると、Difyワークフローを自動的に開始します。
- Googleの変更通知をサブスクライブすることで、ポーリングなしで自動化を同期します。
- ワークフロー内でワイルドカードパターンを使用してファイル名をマッチングすることで、重要なファイルを絞り込むことができます。

## ステップ1：OAuthでGoogleアカウントを接続

![Google Drive Trigger Plugin](./_assets/94938e90f2484db2762e14f8960991f3.png)

1. DifyでGoogle Drive Trigger Pluginを開き、**New Subscription** → **Create with OAuth**をクリックします。
2. 監視したいGoogleアカウントでサインインし、同意画面を承認します。Difyの管理OAuthクライアント（Dify Cloudサービスでホスト）がリダイレクトとトークンストレージを処理します。

> ヒント：デフォルトのスコープは既に変更通知をカバーしています（`https://www.googleapis.com/auth/drive.metadata.readonly https://www.googleapis.com/auth/drive.appdata`）。より広範なアクセスが必要であることがわかっている場合にのみ変更してください。

### オプション：独自のOAuthクライアントを使用

![Google Drive Trigger Plugin](./_assets/da494b82c5a2dd73db3709295fd7a383.png)

組織が独自のGoogle OAuthクレデンシャルの使用を要求する場合：

1. [Google Cloud Console](https://console.cloud.google.com/)にアクセスし、プロジェクトを作成（または再利用）し、**Google Drive API**を有効にします。
2. **APIs & Services → Credentials**で、**OAuth client ID**（Webアプリケーション）を作成します。
3. Difyが認可済みリダイレクトURIを要求したら、サブスクリプションダイアログに表示されているコールバックURLを貼り付け、生成された**Client ID**と**Client Secret**をDifyにコピーして戻します。
4. 同じ同意フローに従って再接続します。今回はプロンプトが表示されたときにカスタムクライアントを使用します。

## ステップ2：監視対象を設定

トリガーサブスクリプションダイアログ内で、Google Driveが更新を送信する方法を微調整できます：

- **Spaces**（`drive`、`appDataFolder`）：関心のあるDriveスペースを選択します。通常のファイル変更が必要な場合は「My Drive」を選択したままにする必要があります。
- **Include removed items**：削除または削除されたアイテムをキャプチャする必要がある場合は有効にします。
- **Restrict to my drive**：ウォッチを個人のMy Driveに制限します。オフのままにすると、共有ドライブまたはあなたと共有されているファイルを監視します。
- **Include items from all drives / Supports all drives**：他のユーザーまたは組織全体が所有する共有ドライブに自動化が反応する必要がある場合は、これらをオンにします。

OAuth handshakeをやり直すことなく、いつでもこれらの設定を再訪してスコープを調整できます。

## ステップ3：ワークフローでトリガーを使用

1. Difyビルダーでワークフローを開き、**Google Drive Change Detected**トリガーを追加します。
2. トリガーノードで、**File name pattern**を使用して、どのファイルがフローを開始するかを決定します。パターンはワイルドカードと複数のエントリをサポートします（例：`*.pdf, reports_??.xlsx`）。
3. オプションで**Change types**（`file`、`drive`）を選択して、ファイルメタデータまたは共有ドライブレベルの変更に焦点を当てます。
4. ワークフローを公開します。Difyはウォッチチャネルをアクティブに保ち、構造化された変更ペイロードをダウンストリームノードに配信します。

> 例：`contracts/*.docx`を使用して、`contracts`フォルダー内のWord契約が変更されたときにのみレビュー自動化を実行します。

## 各トリガーで受信するもの

トリガーは、Google Drive Change APIからの変更オブジェクトのリストを返します。これには以下が含まれます：

- `changes`：各エントリには、`change_type`、`file_id`、`file.name`のようなメタデータ、所有者、タイムスタンプが含まれます。
- `subscription`：ウォッチチャネルの詳細（`channel_id`、有効期限）により、健全性を監視できます。
- `headers` & `body`：検証またはログが必要な場合、Googleによって署名された生のWebhookパッケージ。

これらのフィールドをツール、モデル、または他のワークフローステップに直接渡して、検証、通知、または同期ジョブを構築できます。
