# Outlook Trigger

このトリガーは、Microsoft Outlookからのメール受信イベントを受信し、ワークフローをトリガーします。

## セットアップ

1. [Azure Portal](https://portal.azure.com/#home)にアクセスし、`App Registrations`に移動して新しいアプリケーションを作成します。

![Azure Entra ID](./_assets/images/register_application_01.png)

名前を入力し、サポートされるアカウントタイプとして`Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)`を選択します。`Register`をクリックします。

![Azure Entra ID](./_assets/images/register_application_02.png)

2. `Overview`ページから`Application (client) ID`と`Directory (tenant) ID`をコピーします。`Certificates & secrets`ページで新しいクライアントシークレットを生成し、値をコピーします。

![Azure Entra ID](./_assets/images/get_credentials.png)

3. DifyでこのプラグインをインストールSして、設定ページを開きます。

![Dify](./_assets/images/config_oauth_01.png)

Azure Portalからコピーした値を`Client ID`、`Client Secret`、`Tenant ID`フィールドに入力します。

このダイアログで`redirect_url`が表示されるので、それをコピーしてAzure Entra IDページに戻り、`Authentication`ページに移動し、プラットフォームタイプとして`Web`を選択し、`Redirect URIs`フィールドに`redirect_url`を貼り付けます。`Save`をクリックします。

![Dify](./_assets/images/config_oauth_02.png)

これで、Difyプラグイン設定ページに戻り、`Save and authorize`をクリックしてOAuthフローを開始できます。

このプラグインはMicrosoftログインページにリダイレクトされるので、Microsoftアカウントでログインし、アプリケーションに権限を付与します。

これで、このプラグインをワークフローで使用して、メールを受信したときにトリガーできます。
