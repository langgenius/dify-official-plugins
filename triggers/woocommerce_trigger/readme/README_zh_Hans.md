# WooCommerce 触发器插件

一个将 WooCommerce 商店与 Dify 工作流打通的 Webhook 触发器插件，支持订单、商品、客户与优惠券等事件。

## 配置步骤
![1](./_assets/1.png)
1. 在 WooCommerce 后台 **设置 → 高级 → REST API** 新建 API Key，并记录 Consumer Key/Secret。
2. 在 Dify 安装此插件，填写商店 URL（例如 `https://shop.example.com`），并粘贴 Key/Secret。
3. 选择需要监听的事件，可选地自定义签名密钥。保存后 Dify 会自动创建 WooCommerce Webhook 并校验 `X-WC-Webhook-Signature`。

## 支持的事件
- 订单：创建、更新、删除
- 商品：创建、更新、删除
- 客户：创建、更新、删除
- 优惠券：创建、更新、删除
