# DICOM Reader プラグイン（ツール分割）

このファイルは日本語の説明です。英語版は上位ディレクトリの `README.md` をご覧ください。

## 概要
本プラグインは DICOM の機能を用途別の小さなツールに分割し、必要な処理を選択して実行できます。レスポンスは軽量で LLM に適しています。

## ツール一覧
- dicom_metadata：患者/検査/シリーズ/画像の主要メタデータを抽出、追加タグに対応
- dicom_pixels：画素配列の要約（形状/型/統計）とプレビュー
- dicom_multiframe：マルチフレーム解析、フレーム数・プレビュー
- dicom_hu_correction：RescaleSlope/Intercept による HU 近似補正
- dicom_spatial：空間情報（PixelSpacing、SliceThickness、方向/位置、体素サイズ 等）
- dicom_pixel_ops：基本画素演算（正規化、加減算、クリップ、コントラスト拡張、ボックスブラー）
- dicom_stats：統計量（平均/分散/標準偏差/ヒストグラム）、矩形 ROI 対応
- dicom_volume：間隔×閾値マスクで体積（mm³）推定、マスク内平均強度
- dicom_threshold_mask：閾値によるマスク生成とオーバーレイ表示
- dicom_roi：矩形 ROI の統計（枠付きプレビュー可）
- dicom_model_input：モデル入力形状 [1, C, H, W]（または NHWC）への整形、正規化とプレビュー可

## 共通パラメータ
- `dicom_file`: DICOM Part 10（.dcm）
- `frame_index`: マルチフレーム時の 0 始まりフレーム番号（該当ツール）
- `max_preview_edge`: プレビュー最大辺（32–1024）

## 大きなファイルへの対応
- 可能な場合は `stop_before_pixels` でヘッダのみを読み込んで軽量化
- プレビューは PNG、小さめ優先、1 枚あたり約 8 MB を上限に調整

## プライバシー
同ディレクトリの `PRIVACY.md` を参照してください。
