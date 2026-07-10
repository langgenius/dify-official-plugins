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

3. API 権限を設定します。
`API permissions`ページに移動します。
次の Microsoft Graph 委任権限を追加します。

- `Mail.Read`（委任）
- `offline_access`（委任）

アプリケーション権限は不要です。
組織で管理者の同意が必要な場合は、admin consent を付与します。

4. Difyでこのプラグインをインストールして、設定ページを開きます。

![Dify](./_assets/images/config_oauth_01.png)

`Client ID`、`Client Secret`、`Tenant ID`フィールドに入力します。
`Tenant ID`は、選択したアカウントタイプに合わせて、テナントIDまたはドメイン、`organizations`、`common`のいずれかにします。

このダイアログに表示される`redirect_url`をコピーします。
Azure Entra IDページに戻り、`Authentication`ページに移動します。
プラットフォームの種類として`Web`を選択し、`Redirect URIs`フィールドにコピーした`redirect_url`を貼り付けます。
最後に`Save`をクリックします。

![Dify](./_assets/images/config_oauth_02.png)

これで、Difyプラグイン設定ページに戻り、`Save and authorize`をクリックしてOAuthフローを開始できます。

このプラグインはMicrosoftログインページにリダイレクトします。
Microsoftアカウントでログインし、要求された委任権限を付与します。

これで、このプラグインをワークフローで使用して、メールを受信したときにトリガーできます。

## 共有メールボックスの監視

購読時の「メールボックスアドレス（共有メールボックス）」パラメータには、Microsoft Graph のメールボックス識別子（UPN（例: `support@company.com`）、エイリアス、または GUID）を指定できます。これにより、サインイン済みユーザーの個人受信トレイに加えて、共有/部門のメールボックスも監視できます。パラメータを空のままにすると個人受信トレイを監視し（従来のデフォルト）、OAuth アプリがアクセス権を持つ任意のメールボックスを指定すると共有メールボックスを監視します。

共有メールボックスへのアクセスには既存の `Mail.Read` スコープで十分で、新たな権限は不要です。アプリが共有メールボックスへのアクセス権を持っていない場合、Graph は 403 を返し、トリガーは通常の購読エラーとしてそれを報告します。

Microsoft Graph では購読の `resource` は不変です。稼働中の購読を個人メールボックスから共有メールボックスへ切り替えるには、いったん購読解除してから再購読してください。
