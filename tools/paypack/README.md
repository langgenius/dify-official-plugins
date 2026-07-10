# PayPack — AI Agent 通用支付插件

> 两行代码，让 Dify 里的 AI Agent 自己付钱。

## 功能

| 工具 | 说明 |
|------|------|
| PayPack 支付 | USDC / ETH 链上支付 + CNY 支付宝支付 |
| PayPack 查单 | 查询链上交易或支付宝订单状态 |
| PayPack 退款 | 支付宝订单退款 |

## 安装

在 Dify 中：**插件 → 上传本地插件 → 选择 .difypkg 文件**

如果 Dify 开启了签名验证，在 .env 中设置 

## 配置

### 链上支付模式（USDC/ETH）

| 参数 | 说明 | 示例 |
|------|------|------|
| payment_mode | crypto | crypto |
| private_key | ETH 私钥 | 0x... |
| network | 区块链网络 | base-sepolia |
| spend_limit_daily | AI 每日消费上限 | 10.0 |
| broadcast | 是否真实上链 | true |

### 支付宝模式（CNY）

| 参数 | 说明 | 示例 |
|------|------|------|
| payment_mode | alipay | alipay |
| app_id | 支付宝 APPID | 2021... |
| private_key | 商户私钥（PEM） | -----BEGIN RSA... |
| alipay_public_key | 支付宝公钥（PEM） | -----BEGIN PUBLIC... |
| sandbox | 沙箱模式 | true |

## 使用

在 Dify 工作流中添加 PayPack 节点，LLM 会自动理解支付意图并调用。



## 支持的链

Base Sepolia / Base Mainnet / Ethereum Mainnet / Polygon Mainnet / Arbitrum Mainnet

## Links

- GitHub: https://github.com/rhcjw/paypack
- Gitee: https://gitee.com/rhcjw_com/paypack
- PyPI: https://pypi.org/project/langchain-paypack/
