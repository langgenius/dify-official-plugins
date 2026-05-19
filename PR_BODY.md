# feat(vertex_ai): expose Dify app_id via Vertex AI labels for Cloud Billing

## Why

Dify アプリ単位の Cloud Billing 可視化を可能にするため。同じ Dify
インスタンス上の複数アプリで Vertex AI を共用している環境では、
従来 Cloud Billing 上でアプリごとのコストが追跡できなかった。

## What

`enable_request_metadata=enabled` のとき、`dify_app_id` および `dify_source`
を Vertex AI の `GenerateContentConfig.labels` に乗せる。これにより Cloud
Billing で `labels.dify_app_id` 単位のコストブレイクダウンが可能になる
(ETL 不要)。

スコープ:

- 対象は Gemini ルートのみ (`models/llm/llm.py` の `_generate`)
- ラベルキーは `dify_app_id`, `dify_source` の2つ
- Claude on Vertex (`_generate_anthropic`) / `dify_tenant_id` / `dify_user_id` /
  他プロバイダーは別 PR

実装詳細:

- ラベル値の正規化ヘルパー (`models/llm/_labels.py`):
  GCP の labels 仕様 (lowercase, `[a-z0-9_-]` のみ, 63 文字以内) に沿って
  正規化。UUID は無加工で通る。
- `_generate` 内で `credentials.get("enable_request_metadata") == "enabled"`
  のときのみ labels を組み立てて `config_kwargs["labels"]` にセット。
- `get_current_session` の import は関数内ローカルで、`ImportError` を吸収
  (古い `dify_plugin` でもプラグインが壊れない)。
- 9 件の unit test 追加 (`tests/test_labels.py`)。

## Default behavior

無効。`enable_request_metadata` のデフォルトは `disabled` で、credential を
再設定しない既存ユーザーへの影響は無い。`disabled` のときコードパスは
従来と完全に一致する。

## Dependencies

- langgenius/dify-plugin-sdks #313 のマージ・リリースが必要
  (`get_current_session()` のパブリック API 化)
- 本 PR の `pyproject.toml` は開発期間中 #313 ブランチに pin している
  (`dify_plugin @ git+https://github.com/ryuta-kobayashi-ug/dify-plugin-sdks.git@feat/pass-session-to-model-plugins`)。
  #313 マージ・リリース後に通常の version 指定に戻すコミットを追加する。

## Related

- langgenius/dify #35772 (本体側 issue)
- langgenius/dify-plugin-sdks #311 (SDK 側 issue)
- langgenius/dify #35859 (本体側 PR: contextvars で app_id 伝搬)
- langgenius/dify-plugin-sdks #313 (SDK 側 PR: `get_current_session()` 公開)

## E2E verification

Cloud Billing の `labels.dify_app_id` ブレイクダウンスクショは PR 提出時に
追加予定 (検証中)。ローカルでは:

- 9 件の unit test がパス (`uv run pytest tests/`)
- `build_dify_labels` のスモークテストで UUID/None/空文字/異常文字混入の
  全パスを確認済み
- `from dify_plugin import get_current_session` が #313 ブランチで成功
