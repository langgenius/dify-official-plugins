# Outlook Trigger

此触发器从 Microsoft Outlook 接收邮件接收事件并触发工作流。

## 1.0.0 升级说明

升级后请检查已保存的 `Tenant` 值。
单租户应用填写租户 ID 或域名；仅允许组织账号时填写 `organizations`；只有需要个人 Microsoft 账号时才填写 `common`。
为了兼容已有保存配置，Dify 中该字段仍按密钥样式显示。

## 设置

1. 进入 [Azure Portal](https://portal.azure.com/#home)，前往 `App Registrations` 并创建新应用程序。

![Azure Entra ID](./_assets/images/register_application_01.png)

填写名称，并根据租户安全策略选择支持的账户类型。
如果只允许本公司访问，选择单租户，并在 Dify 中填写 Directory tenant ID。
如果允许多企业组织账号访问，选择任意组织目录账号，并在 Dify 中填写 `organizations`。
只有确实需要个人 Microsoft 账号时，才选择包含个人账号的选项，并在 Dify 中填写 `common`。
点击 `Register`。

![Azure Entra ID](./_assets/images/register_application_02.png)

2. 从 `Overview` 页面复制 `Application (client) ID`。
如果选择了单租户，也复制 `Directory (tenant) ID`。
在 `Certificates & secrets` 页面生成新的客户端密钥并复制该值。

![Azure Entra ID](./_assets/images/get_credentials.png)

3. 配置 API 权限。
进入 `API permissions` 页面。
添加以下 Microsoft Graph 委托权限：

- `Mail.Read`（委托）
- `offline_access`（委托）

不需要添加应用程序权限。
如果您的组织要求管理员同意，请授予 admin consent。

4. 在 Dify 中安装此插件并打开配置页面。

![Dify](./_assets/images/config_oauth_01.png)

填写 `Client ID`、`Client Secret` 和 `Tenant ID` 字段。
`Tenant ID` 应与账户类型选择一致：租户 ID 或域名、`organizations` 或 `common`。

复制此对话框中显示的 `redirect_url`，然后返回 Azure Entra ID 页面。
前往 `Authentication` 页面，选择 `Web` 作为平台类型，并在 `Redirect URIs` 字段中粘贴该 `redirect_url`。
点击 `Save`。

![Dify](./_assets/images/config_oauth_02.png)

现在您可以返回 Dify 插件配置页面并点击 `Save and authorize` 以启动 OAuth 流程。

此插件将您重定向到 Microsoft 登录页面。
请使用您的 Microsoft 账户登录并授予所请求的委托权限。

然后您可以在工作流中使用此插件,在收到电子邮件时触发它。
