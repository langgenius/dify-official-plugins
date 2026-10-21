# 概要

- [設定](#設定)

Geminiは、Googleが提供するマルチモーダルAIモデルファミリーで、テキスト、画像、音声、動画など、さまざまな種類のデータを処理および生成するように設計されています。このプラグインは、単一のAPIキーを介してGeminiモデルへのアクセスを提供し、開発者が多様なマルチモーダルAIアプリケーションを構築できるようにします。

## Gemini 4 Argon

有料の Gemini API キーで `gemini-4-argon` を選択してください。
テキスト、画像、音声、動画、PDF の入力と、テキスト出力、関数呼び出し、構造化出力、Google 検索、URL コンテキスト、コード実行に対応しています。
入力、思考、出力は合計 1,048,576 トークンのコンテキストを共有します。
思考レベルの既定値は Medium で、Low と High も選択できます。
出力上限の既定値は 65,536 トークンです。
上限を増やすと Google GenAI SDK が自動で生成を継続し、残りのコンテキストまで利用できます。
プラグインのリクエストタイムアウトは 15 分です。
長い推論には Dify 側のタイムアウト設定も調整してください。

Standard の導入価格は 2026 年 11 月 30 日まで、入力 100 万トークンあたり 2 ドル、思考を含む出力 100 万トークンあたり 10 ドルです。
Google の公表価格は 2026 年 12 月 1 日からそれぞれ 4 ドルと 20 ドルになり、プラグインの価格設定も更新が必要です。
暗黙的キャッシュに対応していますが、明示的なコンテキストキャッシュには対応していません。
詳細は[発表](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-4-argon/)、[モデル仕様](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon)、[長い出力のガイド](https://ai.google.dev/gemini-api/docs/generate-content/long-decode)、[料金](https://ai.google.dev/gemini-api/docs/pricing#gemini-4-argon)を参照してください。

## 設定
Geminiプラグインをインストールした後、Googleから取得できるAPIキーで設定します。モデルプロバイダー設定にキーを入力して保存します。

![](./_assets/gemini-01.png)

Geminiやその他のビジョンモデルで `MULTIMODAL_SEND_FORMAT` に `url` モードを使用する場合、`Files URL` を設定することで、より良いパフォーマンスを得ることができます。

`Enable request metadata` はオプションで、デフォルトでは無効になっています。これを有効にすると、`dify_app_id` と `dify_source` が `GenerateContentConfig` の `labels` として各 Gemini リクエストに付加され、Cloud Billing で特定の Dify アプリに使用量を帰属させることができます。このオプトインは `generate_content` ルートにのみ適用されます。Interactions API はその課金内訳で labels を表示しないため、意図的に変更されていません。Dify セッションの検索はベストエフォートです。セッションコンテキストが初期化されていない場合、labels は付加されず、リクエストは変更されずに送信されます。

