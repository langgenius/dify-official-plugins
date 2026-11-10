# Microsoft Excel 365 Plugin

**Author**: langgenius  
**Type**: tool  
**Version**: 1.0.0  

## Introduction

This plugin integrates with Microsoft Excel 365, supporting comprehensive spreadsheet operations through Microsoft Graph API. It enables automated management of Excel workbooks and worksheets in platforms like Dify, allowing you to read, write, and manipulate Excel data seamlessly.

### Choose how to authorize

| Mode | Whose workbooks the tools use | Use it for |
|---|---|---|
| **OAuth** | The one person who authorized from the Dify console; everyone using the tool shares that account | A workflow or app on one known account's files |
| **Service Principal** (new in 1.0.0) | Files in a user's OneDrive or a SharePoint site you name, accessed as the app; nobody signs in | Automation on shared workbooks |
| **Each user signs in** (new in 1.0.0) | The workbooks of whoever is chatting with the agent; each user signs in once with their own Microsoft account | A chat agent that many people use ("add this expense to my sheet") |

All three use the same Microsoft Entra app registration and can exist side by side; pick one per agent or workflow node. Every mode also takes an optional SharePoint **Site ID** per tool call.

## Features

This plugin supports comprehensive Excel 365 operations including:

- **File Management**: List all files and folders in OneDrive with filtering options
- **Workbook Management**: List, browse and search Excel workbooks in OneDrive/SharePoint
- **Worksheet Operations**: Create, list and manage worksheets within workbooks
- **Data Reading**: Read cell values from specified ranges with flexible range selection
- **Data Writing**: Update or insert data into cells with 2D array support
- **Data Clearing**: Remove content from specified cell ranges
- **Data Search**: Find specific values within worksheets and get their locations
- **Rows by header** (new in 1.0.0): read rows as `{"Column": value}` objects, append rows, update rows matched on a key column, or update-or-append
- **Tables** (new in 1.0.0): list, add, delete and convert Excel tables; read their columns and rows, append rows, and look up rows by a column value
- **Delete** (new in 1.0.0): workbooks and worksheets

Together these cover the common workbook, worksheet and table operations. `read_worksheet_data` and `write_worksheet_data` remain for raw cell grids.

## Setup

1. Register your application in the [Microsoft Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).


<img src="_assets/azure_portal.png" alt="Azure App Registration" width="300">

2. Create a new application as follows:
    - **Name**: Dify Excel 365 Plugin
    - **Supported account types**: select `Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)`
    - **Redirect URI**: Choose `Web` and set the URI to:
        - For SaaS (cloud.dify.ai) users: please use `https://cloud.dify.ai/console/api/oauth/plugin/langgenius/microsoft_excel365/excel365/tool/callback`
        - For self-hosted users: please use `http://<YOUR LOCALHOST CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/microsoft_excel365/excel365/tool/callback`
        ***Due to the restrictions of the Microsoft OAuth2 flow, redirect URIs must start with `https://` or `http://localhost`.***
        - Enable "Access tokens" and "ID tokens" under "Implicit grant and hybrid flows"

<img src="_assets/redirect_uri.png" alt="Redirect URI" width="300">

3. Copy your **Application (client) ID**

4. Create a new client secret:
    - **Description**: Dify Excel 365 Plugin Secret
    - **Expires**: Whatever duration you prefer (e.g., 1 year, 2 years, etc.)
    - Copy the generated **Value** of the client secret.

<img src="_assets/client_secret.png" alt="Generate Client Secret" width="300">

5. Configure API Permissions:
    - Go to "API permissions"
    - Click "Add a permission" → "Microsoft Graph"
    - Add the following permissions — all **Delegated**, and they must match the scopes requested by the plugin:
        - `offline_access`
        - `User.Read`
        - `Files.ReadWrite`
        - `Files.ReadWrite.All`
        - `Sites.Read.All`
    - Grant admin consent if required

    > Every permission above is listed as *Admin consent required: No* in the [Microsoft Graph permissions reference](https://learn.microsoft.com/en-us/graph/permissions-reference). If your tenant still shows a "Need admin approval" screen during authorization, the tenant's [user consent settings](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/configure-user-consent) restrict user consent, and an administrator has to consent on behalf of the organization.

6. Configure the plugin in Dify:
    - Fill in the **Client ID** and **Client Secret** fields with the values you copied from the Azure Portal.
    - Optional (new in 1.0.0): **Tenant ID** (default `common`, any work or personal account as before; your directory ID limits sign-in to your organization) and **Microsoft Cloud** (Global unless your tenant is in a national cloud).
    - Make sure you have the same redirect URI as specified in the Azure Portal. If not, you will need to update it in the Azure Portal.
    - Click `Save and authorize` to initiate the OAuth flow.

<img src="_assets/setup.png" alt="Setup" width="300">

7. Enjoy using the Microsoft Excel 365 plugin in Dify!

## Service Principal (app-only, new in 1.0.0)

Use this when a workflow should run as the organization rather than as a person: nobody signs in, nothing breaks when someone leaves, and the audit log shows the app.

1. In the app registration, add the Microsoft Graph **Application** permission `Files.ReadWrite.All` and click **Grant admin consent**. It reaches every user's OneDrive and every SharePoint site in the tenant, so treat the client secret accordingly.
2. In Dify, click **Add API Key**, keep **Mode** at *Service Principal*, and fill in **Tenant ID** (your directory ID, not `common`), **Client ID**, **Client Secret** and, optionally, **Default Drive Owner** (the user whose OneDrive holds the workbooks, e.g. `alice@contoso.com`). With a default drive owner, Dify opens that OneDrive to check the permission.
3. Each tool call then needs a location: a **Site ID** (SharePoint), the tool's **Drive Owner** setting (set in the node, never chosen by the LLM), or the credential's default drive owner.

## Each user signs in (for chat agents, new in 1.0.0)

The first time a user needs Excel, the tool returns a Microsoft sign-in link instead of data; the agent passes it on, the user signs in in the browser, comes back and says they are done, and the agent calls the tool again. From then on the tools work on that user's own workbooks, in later conversations too.

1. In the app registration, add the **Delegated** permissions listed under Setup (`offline_access`, `User.Read`, `Files.ReadWrite`, `Files.ReadWrite.All`, `Sites.Read.All`) and click **Grant admin consent** so users never see a consent screen.
2. In Dify, open the plugin's details → **Endpoints**, click **+**, enter a name (nothing else to fill in), and copy the endpoint URL. It looks like `https://<your-dify-domain>/e/<id>/excel/callback`. If it starts with `http://localhost`, your self-hosted Dify still uses the default `ENDPOINT_URL_TEMPLATE=http://localhost/e/{hook_id}`: set `ENDPOINT_URL_TEMPLATE=https://<your-dify-domain>/e/{hook_id}` in `docker/.env` and restart the API, or replace `http://localhost` with your Dify address by hand.

   <img src="_assets/dify-endpoint-url.png" alt="Endpoint URL" width="360">

3. In the app registration, open **Authentication** → **Add Redirect URI** → **Web**, paste the endpoint URL and click **Configure**. A mismatch shows up later as error `AADSTS50011` on the Microsoft sign-in page.
4. In Dify, click **Add API Key**, set **Mode** to *Each user signs in*, and fill in **Tenant ID**, **Client ID**, **Client Secret** (the secret's *Value*) and **Sign-in Callback URL**. Leave **Default Drive Owner** empty.
5. In the agent, add the Excel tools you want and **Sign Out of Excel**, and choose this authorization in the credential menu. Instructions like these work well:

```
You can use the Excel tools on the current user's own workbooks.
- Find workbooks with list_workbooks, sheets with list_worksheets, tables with excel_list_tables.
- Read with read_worksheet_data or excel_get_table_rows; add rows with excel_append_rows or excel_append_table_rows; update rows by a key column with excel_upsert_rows.
- If a tool says the user needs to sign in and returns a link, give the link to the user exactly as returned. Ask them to open it, sign in with their own Microsoft account, and reply "done" when finished. After they reply, call the same tool again.
- Before deleting a workbook, worksheet or table, tell the user what will be deleted and ask them to confirm.
- Never make up data. If a tool returns an error, tell the user what it says.
- If the user asks to sign out or switch accounts, call excel_sign_out.
```

With Outlook, Teams and OneDrive in the same agent, each has its own per-user authorization:

<img src="_assets/agent-credentials.png" alt="Outlook, Teams, OneDrive and Excel, each with its own per-user authorization" width="600">

What users see: the first request returns a sign-in link; after signing in, the first answer names the account used.

<img src="_assets/chat-sign-in-link.png" alt="Sign-in link" width="600">

<img src="_assets/chat-signed-in.png" alt="Answer after signing in, naming the account" width="600">

What to know:
- Each user's tokens are kept in the plugin's storage, encrypted with a key derived from the client secret. They never reach the agent or the logs. The endpoint only holds a one-time authorization code briefly; turning it into a token also needs the client secret and a PKCE verifier it never sees.
- Users stay signed in while they keep using it (the access token is renewed hourly; Microsoft's refresh token expires after about 90 days unused). They sign in again after signing out, a password change, an administrator revoking their sessions, or a client secret rotation.
- Users are told apart by Dify's user ID. It is stable in the console and for Service API callers that always send the same `user`; in a public web app without login, each browser is a new anonymous user. The Service API `user` value is chosen by the caller, so call the API only from a trusted backend.
- Each plugin keeps its own sign-in: with Outlook, Teams or OneDrive in the same agent, a user signs in once for each, and signing out of one leaves the others signed in.
- A user could send their own sign-in link to a colleague, whose account would then be connected to the sender's chat. The **Signed in** page warns about this and offers to cancel; an administrator can end any connection by revoking the user's sessions in Entra.

## Scopes (Hard-coded)

The plugin uses the following Microsoft Graph delegated scopes (hard-coded in the provider):
- `offline_access`: Maintain access to data you have given it access to
- `User.Read`: Sign in and read the user profile (used by the credential validation call `GET /me`)
- `Files.ReadWrite`: Read and write user's files
- `Files.ReadWrite.All`: Read and write all files the signed-in user can access (required for writing to SharePoint Site drives)
- `Sites.Read.All`: Read SharePoint site collections and related files/drives (requested since `site_id` support was added; the drive endpoints accept it as an alternative to `Files.ReadWrite.All`)

*Each user signs in* requests the same delegated scopes. *Service Principal* uses the application permission `Files.ReadWrite.All` instead.

Note: Scopes are defined in `provider/microsoft_excel365.py` and requested during OAuth. They must be registered as API permissions on the Azure app registration as well; otherwise Entra ID asks for consent again on every authorization.

## SharePoint Site Support (site_id)

By default, all tools operate on the signed-in user’s OneDrive using the Graph endpoint `…/me/drive`.

If you need to access or edit files that live under a SharePoint Site, you can provide an optional parameter `site_id` to target that Site’s drive. When `site_id` is present, the tools will switch to the Graph endpoint `…/sites/{site_id}/drive`.

- When to use: only when you need to access/edit content inside a SharePoint Site.
- How to find: obtain the Site’s ID from Microsoft Graph or the SharePoint admin/UI as appropriate. Quick tip: append `/_api/site/id` to your SharePoint site URL (e.g., `https://yourdomain.sharepoint.com/sites/YourSite/_api/site/id`) to get the `site_id`.
- Required permissions: `Sites.Read.All` alone only allows reading. The writing tools (`write_worksheet_data`, `clear_worksheet_data`, `create_worksheet`) also need `Files.ReadWrite.All`, because `Files.ReadWrite` is limited to the signed-in user's own OneDrive.

Tools that accept `site_id` (optional):
- list_all_files
- list_workbooks
- list_worksheets
- read_worksheet_data
- write_worksheet_data
- clear_worksheet_data
- create_worksheet
- search_worksheet_data

## Tool Descriptions

### list_all_files
List all files and folders in OneDrive with optional filtering.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- folder_path (string, optional): The folder path to list (use 'root' for root folder, 'recent' for recent files, or 'id:FOLDER_ID' for specific folder). Default is "root".
- file_type (select, optional): Filter by file type. Options: "all", "excel", "folders". Default is "all".
- max_results (number, optional): Maximum number of items to return (default: 50, max: 200).

### list_workbooks
List all Excel workbooks accessible to the user in OneDrive or SharePoint.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- folder_id (string, optional): The ID of the folder to list workbooks from.
- search_query (string, optional): Search for workbooks by name.
- max_results (number, optional): Maximum number of workbooks to return (default: 20, max: 100).

### list_worksheets
List all worksheets in a specified Excel workbook.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- workbook_id (string): The ID of the Excel workbook.

### read_worksheet_data
Read data from a specified range in an Excel worksheet.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- workbook_id (string): The ID of the Excel workbook.
- worksheet_name (string): The name of the worksheet to read from.
- range (string, optional): The cell range to read (e.g., A1:D10). Default is A1:Z100.

### write_worksheet_data
Write data to a specified range in an Excel worksheet.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- workbook_id (string): The ID of the Excel workbook.
- worksheet_name (string): The name of the worksheet to write to.
- range (string): The cell range to write to (e.g., A1:D10).
- values (string): The values to write as a 2D array in JSON format.

### clear_worksheet_data
Clear data from a specified range in an Excel worksheet.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- workbook_id (string): The ID of the Excel workbook.
- worksheet_name (string): The name of the worksheet to clear data from.
- range (string): The cell range to clear (e.g., A1:D10).

### create_worksheet
Create a new worksheet in an Excel workbook.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- workbook_id (string): The ID of the Excel workbook.
- worksheet_name (string): The name for the new worksheet.

### search_worksheet_data
Search for specific values in an Excel worksheet.

**Parameters:**
- site_id (string, optional): Only required when accessing a SharePoint Site drive.
- workbook_id (string): The ID of the Excel workbook.
- worksheet_name (string): The name of the worksheet to search in.
- search_value (string): The value to search for.
- range (string, optional): The cell range to search in (e.g., A1:Z1000). Default is A1:Z1000.

### New in 1.0.0

All take `workbook_id` and the optional `site_id`; with a Service Principal, also the **Drive Owner** setting. Rows can be objects keyed by column header (`[{"Name": "Kim", "Score": 90}]`; left-out columns stay empty) or lists of cell values.

| Tool | Operation | What it does |
|---|---|---|
| `excel_append_rows` | Worksheet: Append | Adds rows below the data on a worksheet; on an empty sheet, object keys become the header row |
| `excel_get_rows` | Worksheet: Get Rows | Rows as objects keyed by the header row; reads the used range unless a range is given, with Header Row / First Data Row (default 500 rows, up to 5000) |
| `excel_update_rows` | Worksheet: Update | Updates rows whose `key_column` matches (only the given columns change); never appends, reports keys with no match. **Update All Matches** option |
| `excel_upsert_rows` | Worksheet: Append or Update | Updates rows whose `key_column` matches (only the given columns change) and appends the others. **Update All Matches** option |
| `excel_delete_worksheet` | Worksheet: Delete | Deletes a worksheet |
| `excel_delete_workbook` | Workbook: Delete | Deletes a workbook file (to the recycle bin) |
| `excel_list_tables` | (table picker) | Lists the tables in a workbook and their worksheets |
| `excel_add_table` | Table: Add | Turns a range into a table, optionally named |
| `excel_delete_table` | Table: Delete | Deletes a table and its data |
| `excel_convert_table_to_range` | Table: Convert to Range | Turns a table back into plain cells, keeping the data |
| `excel_get_table_columns` | Table: Get Columns | The table's column names |
| `excel_get_table_rows` | Table: Get Rows | Rows as objects keyed by column name (default 100, up to 5000) |
| `excel_append_table_rows` | Table: Append | Adds rows at the end of a table |
| `excel_lookup_table` | Table: Lookup | Rows where a column equals a value; **Return All Matches** (default) or only the first |
| `excel_sign_out` | – | *Each user signs in* only: forgets the current user's Excel sign-in |

The new tools carry an `excel_` prefix because Dify's agent requires tool names to be unique across all the plugins an agent uses.

## Output variables (new in 1.0.0)

Besides `text` and `json` (unchanged), every tool returns typed variables that later workflow nodes can pick directly. Every tool has `success` (boolean) and `error` (string, empty on success).

| Tool | Variables (besides `success`, `error`) |
|---|---|
| list_all_files | `items`, `count` |
| list_workbooks | `workbooks`, `count` |
| list_worksheets | `worksheets`, `count` |
| create_worksheet | `worksheet_id`, `name`, `position` |
| read_worksheet_data | `values`, `address`, `row_count`, `column_count` |
| write_worksheet_data | `address`, `rows_written`, `columns_written` |
| clear_worksheet_data | `range_cleared` |
| search_worksheet_data | `matches`, `match_count` |
| excel_append_rows | `address`, `rows_appended` |
| excel_get_rows | `rows`, `columns`, `count`, `has_more`, `address` |
| excel_update_rows | `rows_updated`, `not_found` |
| excel_upsert_rows | `rows_updated`, `rows_appended` |
| excel_delete_worksheet | `worksheet_name` |
| excel_delete_workbook | `workbook_id` |
| excel_list_tables | `tables`, `count` |
| excel_add_table | `table_id`, `name` |
| excel_delete_table | `table` |
| excel_convert_table_to_range | `address` |
| excel_get_table_columns | `columns`, `count` |
| excel_get_table_rows | `rows`, `count`, `has_more` |
| excel_append_table_rows | `rows_appended` |
| excel_lookup_table | `rows`, `count` |
| excel_sign_out | `signed_out` |

## PRIVACY

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

Last updated: September 15, 2026
