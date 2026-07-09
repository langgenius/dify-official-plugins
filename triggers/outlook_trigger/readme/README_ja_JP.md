# Outlook Trigger

このトリガーは、Microsoft Outlookからのメール受信イベントを受信し、ワークフローをトリガーします。

## 1.0.0 アップグレードノート

アップグレード後、保存済みの `Tenant` 値を確認してください。
シングルテナントの場合はテナントIDまたはドメイン、職場または学校アカウントのみの場合は `organizations`、個人の Microsoft アカウントが必要な場合のみ `common` を使います。
既存の保存済み設定との互換性のため、Dify ではこのフィールドをシークレット形式のまま表示します。

## セットアップ

1. [Azure Portal](https://portal.azure.com/#home)にアクセスし、`App Registrations`に移動して新しいアプリケーションを作成します。

![Azure Entra ID](./_assets/images/register_application_01.png)

名前を入力し、テナントのセキュリティポリシーに合うサポート対象アカウントタイプを選択します。
自社のみのアクセスにする場合は、シングルテナントを選択し、Dify に Directory tenant ID を入力します。
組織アカウントのマルチテナントアクセスにする場合は、任意の組織ディレクトリのアカウントを選択し、Dify に `organizations` を入力します。
個人の Microsoft アカウントが必要な場合だけ、個人アカウントを含むオプションを選択し、Dify に `common` を入力します。
`Register`をクリックします。

![Azure Entra ID](./_assets/images/register_application_02.png)

2. `Overview`ページから`Application (client) ID`をコピーします。
シングルテナントを選択した場合は、`Directory (tenant) ID`もコピーします。
`Certificates & secrets`ページで新しいクライアントシークレットを生成し、値をコピーします。

![Azure Entra ID](./_assets/images/get_credentials.png)

3. Difyでこのプラグインをインストールして、設定ページを開きます。

![Dify](./_assets/images/config_oauth_01.png)

`Client ID`、`Client Secret`、`Tenant ID`フィールドに入力します。
`Tenant ID`は、選択したアカウントタイプに合わせて、テナントIDまたはドメイン、`organizations`、`common`のいずれかにします。

このダイアログで`redirect_url`が表示されるので、それをコピーしてAzure Entra IDページに戻り、`Authentication`ページに移動し、プラットフォームタイプとして`Web`を選択し、`Redirect URIs`フィールドに`redirect_url`を貼り付けます。`Save`をクリックします。

![Dify](./_assets/images/config_oauth_02.png)

これで、Difyプラグイン設定ページに戻り、`Save and authorize`をクリックしてOAuthフローを開始できます。

このプラグインはMicrosoftログインページにリダイレクトされるので、Microsoftアカウントでログインし、アプリケーションに権限を付与します。

これで、このプラグインをワークフローで使用して、メールを受信したときにトリガーできます。
