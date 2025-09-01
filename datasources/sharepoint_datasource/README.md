# SharePoint Datasource Plugin

**Author**: langgenius
**Version**: 0.0.1
**Type**: datasource

## Introduction

This plugin integrates with Microsoft SharePoint, supporting operations such as retrieving files and documents from your SharePoint sites. It enables automated access to your SharePoint content in platforms like Dify.

## Datasources

- **Documents in Site**
  - Get files from your Document Library in SharePoint sites.
- **Documents in Group**
  - Get files from your Document Library in SharePoint sites, organized by groups, such as Teams-connected sites.

## Setup

> **IMPORTANT**: Only Microsoft Enterprise users can use Sharepoint. To use this plugin, you need the approval of your organization administrator.

1. Register your application in the [Microsoft Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).

2. Create a new application as follows:
    - **Name**: Dify SharePoint Plugin
    - **Supported account types**: select `Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)`
    - **Redirect URI**: Choose `Web` and set the URI to:
        - For SaaS (cloud.dify.ai) users: please use `https://cloud.dify.ai/console/api/oauth/plugin/langgenius/sharepoint_datasource/sharepoint/datasource/callback`
        - For self-hosted users: please use `http://<YOUR LOCALHOST CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/sharepoint_datasource/sharepoint/datasource/callback`
        ***Due to the restrictions of the Microsoft OAuth2 flow, redirect URIs must start with `https://` or `http://localhost`.***
        - Enable "Access tokens" and "ID tokens" under "Implicit grant and hybrid flows"

3. Copy your **Application (client) ID**

4. Create a new client secret:
    - **Description**: Dify SharePoint Plugin Secret
    - **Expires**: Whatever duration you prefer (e.g., 1 year, 2 years, etc.)
    - Copy the generated **Value** of the client secret.

5. Configure API permissions:
    - Go to "API permissions" section
    - Add the following Microsoft Graph permissions:
        - `User.Read` (delegated)
        - `Sites.Read.All` (delegated)
        - `Files.Read.All` (delegated)
        - `Group.Read.All` (delegated, required if you want to access files in groups)
    - Grant admin consent for these permissions

6. Configure the plugin in Dify:
    - Fill in the **Client ID** and **Client Secret** fields with the values you copied from the Azure Portal.
    - Enter your **SharePoint Subdomain** (e.g., "mycompany" for mycompany.sharepoint.com)
    - Make sure you have the same redirect URI as specified in the Azure Portal. If not, you will need to update it in the Azure Portal.
    - Click `Save and authorize` to initiate the OAuth flow.

7. Enjoy using the SharePoint datasource plugin in Dify!

## Datasource Descriptions

### SharePoint File Retrieval
Retrieve files and documents from your SharePoint sites. The plugin supports:
- Accessing files from SharePoint document libraries
- Retrieving files from specific SharePoint sites
- Supporting various file formats (documents, spreadsheets, presentations, etc.)

**Parameters:**
- SharePoint subdomain: Your organization's SharePoint subdomain
- File path: The path to the file you want to retrieve
- Site URL: The specific SharePoint site URL (optional)

## PRIVACY

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

Last updated: September 1, 2025
