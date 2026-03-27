# Outlook Trigger

此触发器从 Microsoft Outlook 接收邮件接收事件并触发工作流。

## 设置

1. 进入 [Azure Portal](https://portal.azure.com/#home)，前往 `App Registrations` 并创建新应用程序。

![Azure Entra ID](./_assets/images/register_application_01.png)

填写名称并选择 `Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)` 作为支持的账户类型。点击 `Register`。

![Azure Entra ID](./_assets/images/register_application_02.png)

2. 从 `Overview` 页面复制 `Application (client) ID` 和 `Directory (tenant) ID`。在 `Certificates & secrets` 页面生成新的客户端密钥并复制该值。

![Azure Entra ID](./_assets/images/get_credentials.png)

3. 在 Dify 中安装此插件并打开配置页面。

![Dify](./_assets/images/config_oauth_01.png)

使用从 Azure Portal 复制的值填写 `Client ID`、`Client Secret` 和 `Tenant ID` 字段。

您将在此对话框中获得 `redirect_url`，复制它并返回 Azure Entra ID 页面，前往 `Authentication` 页面，选择 `Web` 作为平台类型，在 `Redirect URIs` 字段中粘贴 `redirect_url`。点击 `Save`。

![Dify](./_assets/images/config_oauth_02.png)

现在您可以返回 Dify 插件配置页面并点击 `Save and authorize` 以启动 OAuth 流程。

此插件将重定向您到 Microsoft 登录页面，使用您的 Microsoft 账户登录并授予应用程序权限。

然后您可以在工作流中使用此插件,在收到电子邮件时触发它。
