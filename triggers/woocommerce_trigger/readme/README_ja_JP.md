# WooCommerce トリガープラグイン

WooCommerce ストアの Webhook を自動作成し、Dify ワークフローを起動できるトリガープラグインです。注文 / 商品 / 顧客 / クーポンの変更をカバーします。

## 設定手順
![1](./_assets/1.png)
1. WooCommerce 管理画面の **設定 → 詳細 → REST API** で API キーを作成し、Consumer Key / Secret を控えます。
2. Dify に本プラグインをインストールし、店舗 URL（例: `https://shop.example.com`）と取得した Key/Secret を入力します。
3. 監視したいイベントと署名シークレット（任意）を設定してサブスクリプションを保存すると、Dify が Webhook を作成し `X-WC-Webhook-Signature` を検証します。

## サポートするイベント
- 注文: 作成 / 更新 / 削除
- 商品: 作成 / 更新 / 削除
- 顧客: 作成 / 更新 / 削除
- クーポン: 作成 / 更新 / 削除
