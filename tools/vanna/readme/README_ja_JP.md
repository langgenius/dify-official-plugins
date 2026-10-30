# 概要
Vanna.aiは、ユーザーと複雑なSQLデータベース間のやり取りを簡素化するために設計された、革新的なAI駆動プラットフォームです。

# 設定
## APIキーの取得
1. Vanna.aiでアカウントを作成してログインします。
2. API KeysからAPIキーをコピーします。

## Vanna.AIツールの設定
1. MarketplaceからVanna.AIをインストールします。
![](../_assets/vanna_install.png)
2. ワークフローにVanna.AIノードを追加します。
3. Vanna.AI APIキーを入力します。
4. データベース設定を入力します。
![](../_assets/vanna_configure.png)

## データベース接続

SQLite と DuckDB は、既存のローカルデータベースファイルまたは HTTP(S) ダウンロード URL に対応しています。
DuckDB は `:memory:`、`md:`、`motherduck:` 接続にも対応しています。
Microsoft SQL Server では、URL/Host/DSN に ODBC 接続文字列を入力してください。
プラグイン実行環境には unixODBC と対応する SQL Server ODBC ドライバーが必要です。
