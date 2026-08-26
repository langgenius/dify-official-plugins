# ERNIE Image

このファイルは日本語の説明です。英語版は上位ディレクトリの `README.md`
をご覧ください。

Baidu AI Studio の OpenAI 互換 Images API を呼び出し、**ERNIE Image** と
**ERNIE Image Turbo** でテキストから画像を生成する Dify ツールです。

## モデル

| モデル | 公式モデルガイダンス |
|--------|------------------------|
| `ernie-image-turbo` | 速度と美観に最適化された蒸留モデル。通常 8 推論ステップで、プラグインのデフォルトです。 |
| `ernie-image` | 汎用能力と指示追従性を重視した SFT モデル。通常 50 推論ステップです。 |

推論設定はホスト API が制御します。上記のステップ数は公式モデルの説明であり、
プラグインのパラメータではありません。

## セットアップ

1. <https://aistudio.baidu.com> にログインし、「パーソナルセンター →
   アクセストークン」からアクセストークンを発行します。
2. Dify でこのプラグインをインストールし、上記のトークンで認証します。

## パラメータ

- `prompt`（必須）: 生成したい画像のテキスト説明（最大 2048 文字）。
- `model`: `ernie-image-turbo`（デフォルト）または `ernie-image`。
- `size`: 現行の公式解像度 `1024x1024`、`848x1264`、`768x1376`、
  `896x1200`、`1264x848`、`1376x768`、`1200x896` のいずれか。
  デフォルトは `1024x1024`、Baidu の推奨は `1376x768` です。既存の
  Dify ワークフローとの互換性のため、以前公開した解像度も実行時には受け付けます。
- `n`: 生成枚数（1–4）。デフォルトは `1`。
- `seed`: 再現可能な出力のための任意の整数シード。
- `watermark`: 出力にモデル透かしを付けるかどうか。デフォルトは `false`。

`n` と `seed` は AI Studio endpoint の互換拡張です。現在公開されている
Qianfan のリクエスト仕様では `prompt`、`model`、`size`、`watermark` が
文書化されています。

出力: ダウンロードに成功した画像は PNG blob として返され、レスポンスの
`id`、`created`、AI Studio の `trace_id`、URL、`revised_prompt` を含む
JSON サマリーが添付されます。生成 URL の有効期間は公式文書で 24 時間と
されているため、永続的な出力には blob を使用してください。

## 互換性と検証

- リクエスト前にモデル、解像度、プロンプト長、生成枚数、整数シードを検証します。
- AI Studio（`errorCode` / `errorMsg`）と現行 OpenAI 互換
  （`code` / `message` / `type`）のエラー形式に対応します。
- 1 枚の画像取得に失敗しても、他の画像と JSON サマリーは保持されます。

## 公式リファレンス

- [ERNIE-Image 公式モデルカード](https://aistudio.baidu.com/modelsdetail/46031)
- [ERNIE-Image-Turbo 公式モデルカード](https://aistudio.baidu.com/modelsdetail/46030/intro)
- [ERNIE-Image-Turbo API リファレンス](https://cloud.baidu.com/doc/qianfan-api/s/Imo9g5a6a)

## プライバシー

同ディレクトリの `PRIVACY.md` を参照してください。
