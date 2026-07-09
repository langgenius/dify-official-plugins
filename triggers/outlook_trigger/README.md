# Outlook Trigger

This trigger receives email received events from Microsoft Outlook and triggers a workflow.

## Upgrade Notes for 1.0.0

Review the saved `Tenant` value after upgrading.
Use a tenant ID or domain for single-tenant apps, `organizations` for work or school accounts only, or `common` only when personal Microsoft accounts are required.
The field remains secret-style in Dify for compatibility with existing saved configurations.

## Set up

1. Enter [Azure Portal](https://portal.azure.com/#home), head to `App Registrations` and create a new application.

![Azure Entra ID](./_assets/images/register_application_01.png)

Fill with a name and choose the supported account type that matches your tenant policy.
For company-only access, choose single tenant and use the Directory tenant ID in Dify.
For organization-account multi-tenant access, choose accounts in any organizational directory and enter `organizations` in Dify.
Use the personal Microsoft accounts option only when personal accounts are required, then enter `common` in Dify.
Click `Register`.

![Azure Entra ID](./_assets/images/register_application_02.png)

2. Copy the `Application (client) ID` from the `Overview` page.
Copy the `Directory (tenant) ID` too if you chose single tenant.
Generate a new client secret in the `Certificates & secrets` page and copy the value.

![Azure Entra ID](./_assets/images/get_credentials.png)

3. Install this plugin in Dify and open configuration page.

![Dify](./_assets/images/config_oauth_01.png)

Fill in the `Client ID`, `Client Secret`, and `Tenant ID` fields.
The `Tenant ID` value should match your account type choice: your tenant ID or domain, `organizations`, or `common`.

You'll get a `redirect_url` in this dialog, copy it and go back to the Azure Entra ID page, head to `Authentication` page, select `Web` as the platform type, add paste the `redirect_url` in the `Redirect URIs` field. Click `Save`.

![Dify](./_assets/images/config_oauth_02.png)

Now you can go back to the Dify plugin configuration page and click `Save and authorize` to initiate the OAuth flow.

This plugin will redirect you to the Microsoft login page, login with your Microsoft account and grant the permissions to the application.

Then you can use this plugin in a workflow to trigger it when you receive an email.

## Monitoring a shared mailbox

The `Mailbox Address (shared mailbox)` parameter on the subscription accepts a Microsoft Graph mailbox identifier — UPN (`support@company.com`), alias, or GUID — so the trigger can watch a shared or departmental mailbox in addition to the signed-in user's personal Inbox. Leave the parameter empty to monitor the personal Inbox (the historical default), or fill in any mailbox your OAuth app has access to.

The existing `Mail.Read` scope is sufficient for shared-mailbox access; no new permissions are required. Graph returns 403 if your app lacks access to the shared mailbox, and the trigger surfaces that as a normal subscription error.

Microsoft Graph treats `resource` as immutable on an existing subscription. To switch a live subscription from personal to shared, unsubscribe and resubscribe.
