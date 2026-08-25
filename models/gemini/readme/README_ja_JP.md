# 概要

- [設定](#設定)

Geminiは、Googleが提供するマルチモーダルAIモデルファミリーで、テキスト、画像、音声、動画など、さまざまな種類のデータを処理および生成するように設計されています。このプラグインは、単一のAPIキーを介してGeminiモデルへのアクセスを提供し、開発者が多様なマルチモーダルAIアプリケーションを構築できるようにします。

## 設定
Geminiプラグインをインストールした後、Googleから取得できるAPIキーで設定します。モデルプロバイダー設定にキーを入力して保存します。

![](./_assets/gemini-01.png)

Geminiやその他のビジョンモデルで `MULTIMODAL_SEND_FORMAT` に `url` モードを使用する場合、`Files URL` を設定することで、より良いパフォーマンスを得ることができます。

`Enable request metadata` はオプションで、デフォルトでは無効になっています。これを有効にすると、`dify_app_id` と `dify_source` が `GenerateContentConfig` の `labels` として各 Gemini リクエストに付加され、Cloud Billing で特定の Dify アプリに使用量を帰属させることができます。このオプトインは `generate_content` ルートにのみ適用されます。Interactions API はその課金内訳で labels を表示しないため、意図的に変更されていません。Dify セッションの検索はベストエフォートです。セッションコンテキストが初期化されていない場合、labels は付加されず、リクエストは変更されずに送信されます。

