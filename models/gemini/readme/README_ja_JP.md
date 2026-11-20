# 概要

- [設定](#設定)

Geminiは、Googleが提供するマルチモーダルAIモデルファミリーで、テキスト、画像、音声、動画など、さまざまな種類のデータを処理および生成するように設計されています。このプラグインは、単一のAPIキーを介してGeminiモデルへのアクセスを提供し、開発者が多様なマルチモーダルAIアプリケーションを構築できるようにします。

## Gemini 4

Carbon、Neon、Hydrogen、Argon はテキスト、画像、音声、動画、PDF を入力できます。
4 モデルともテキスト出力、関数呼び出し、構造化出力、Google 検索、URL コンテキスト、コード実行に対応します。
Carbon、Neon、Argon には有料の API キーが必要です。
入力、思考、出力を合わせて 1,048,576 トークンまで利用できます。
出力上限の初期値は 65,536 です。上限を引き上げると、SDK は残りのコンテキストの範囲内で生成を自動的に継続します。
API リクエストごとのタイムアウトは 15 分です。

| モデル | 思考レベルの初期値 | その他のレベル | 100 万トークン当たりの標準料金（入力 / 出力、米ドル） |
| --- | --- | --- | --- |
| Carbon、Argon | Medium | Low、High | 2026 年 11 月 30 日まで 2 / 10、以降 4 / 20 |
| Neon | High | Low、Medium、Xhigh | 3 / 15 |
| Hydrogen | High | Low、Medium、Xhigh | 1.50 / 7.50 |

暗黙キャッシュの読み取り料金は入力料金の 5% です。出力には思考トークンを含みます。[公式料金表](https://aistudio.google.com/docs/pricing) · [長い出力](https://aistudio.google.com/docs/long-decode)

## 設定
Geminiプラグインをインストールした後、Googleから取得できるAPIキーで設定します。モデルプロバイダー設定にキーを入力して保存します。

![](./_assets/gemini-01.png)

Geminiやその他のビジョンモデルで `MULTIMODAL_SEND_FORMAT` に `url` モードを使用する場合、`Files URL` を設定することで、より良いパフォーマンスを得ることができます。

`Enable request metadata` はオプションで、デフォルトでは無効になっています。これを有効にすると、`dify_app_id` と `dify_source` が `GenerateContentConfig` の `labels` として各 Gemini リクエストに付加され、Cloud Billing で特定の Dify アプリに使用量を帰属させることができます。このオプトインは `generate_content` ルートにのみ適用されます。Interactions API はその課金内訳で labels を表示しないため、意図的に変更されていません。Dify セッションの検索はベストエフォートです。セッションコンテキストが初期化されていない場合、labels は付加されず、リクエストは変更されずに送信されます。

