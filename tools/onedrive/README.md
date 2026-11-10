
# Microsoft OneDrive Plugin

**Author**: langgenius
**Version**: 1.0.0
**Type**: plugin

## Introduction

This plugin integrates with Microsoft OneDrive, enabling you to search, retrieve, upload, and delete files or folders directly from Dify. It allows automated file management and access to your OneDrive storage through Dify workflows.

### Choose how to authorize

| Mode | Whose OneDrive the tools use | Use it for |
|---|---|---|
| **OAuth** | The one person who signed in from the Dify console; everyone using the tool shares that OneDrive | A workflow or app that works on one known OneDrive |
| **Service Principal** (0.1.0) | A user's OneDrive you name, accessed as the app itself; nobody signs in | Automation on a service account's or a team member's OneDrive |
| **Each user signs in** (1.0.0) | The OneDrive of whoever is chatting with the agent; each user signs in once with their own Microsoft account | A chat agent that many people use ("find my Q3 report", "save this to my OneDrive") |

All three use the same Microsoft Entra app registration and can exist side by side; pick one per agent or workflow node.

## Setup

1. Register your application in the [Microsoft Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).

<p align="center">
    <img src="_assets/azure_portal.png" alt="Azure Portal" width="400" />
</p>

2. Create a new application as follows:
    - **Name**: Dify OneDrive Plugin
    - **Supported account types**: select
        ```
        Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)
        ```
    - **Redirect URI**: Choose `Web` and set the URI to:
        - For SaaS (cloud.dify.ai) users: please use
        ```
        https://cloud.dify.ai/console/api/oauth/plugin/langgenius/onedrive/microsoft_onedrive/tool/callback
        ```
        - For self-hosted users: please use
        ```
        http://<YOUR LOCALHOST CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/onedrive/microsoft_onedrive/tool/callback
        ```
        - ***Due to the restrictions of the Microsoft OAuth2 flow, redirect URIs must start with `https://` or `http://localhost`.***
        - Enable "Access tokens" and "ID tokens" under "Implicit grant and hybrid flows"

<p align="center">
        <img src="_assets/register_app.png" alt="Azure Portal" width="500">
</p>

3. Copy your **Application (client) ID**

<p align="center">
    <img src="_assets/client_id.png" alt="Azure Portal" width="600">
</p>

4. Create a new client secret:
    - **Description**: Dify OneDrive Plugin Secret
    - **Expires**: Whatever duration you prefer (e.g., 1 year, 2 years, etc.)
    - Copy the generated **Value** of the client secret.

<p align="center">
    <img src="_assets/client_secret.png" alt="Azure Portal" width="600">
</p>

5. Review the delegated Microsoft Graph permissions requested during authorization:
    - `Files.Read.All`: Read files that the signed-in user can access for file retrieval and search.
    - `Files.ReadWrite.All`: Read, create, update, and delete files that the signed-in user can access for upload and delete operations.
    - `Files.ReadWrite.All` applies to every file the signed-in user can access, not only files created through Dify.
    - Review or pre-approve these permissions in Microsoft Entra ID according to your organization's consent policy.
    - See the [Microsoft Graph permissions reference](https://learn.microsoft.com/graph/permissions-reference#filesreadwriteall) for the complete permission definitions.

6. Configure the plugin in Dify:
    - Fill in the **Client ID** and **Client Secret** fields with the values you copied from the Azure Portal.
    - **Tenant ID** (new in 0.1.0): leave it as `common` for a multi-tenant app (or personal accounts). If your app registration is **single-tenant** ("Accounts in this organizational directory only"), enter your directory (tenant) ID or domain; with `common` Microsoft rejects the sign-in with `AADSTS50194`.
    - **Microsoft Cloud** (new in 0.1.0): keep Global unless your tenant is in a national cloud (US Government, US Government DoD, China operated by 21Vianet).
    - Make sure you have the same redirect URI as specified in the Azure Portal. If not, you will need to update it in the Azure Portal.
    - Click `Save and authorize` to initiate the OAuth flow.

7. Enjoy using the Microsoft OneDrive plugin in Dify!

<p align="center">
    <img src="_assets/setup.png" alt="Plugin Configuration" width="45%">
    <img src="_assets/result-dify.png" alt="Plugin Configuration" width="45%">
</p>


## Service Principal (app-only, new in 0.1.0)

Use this when a workflow should run as the organisation rather than as a person: no user signs in, nothing breaks when someone leaves, and the audit log shows the app.

1. In the app registration, add the Microsoft Graph **Application** permissions (not Delegated) `Files.ReadWrite.All` and, for **Search File or Folder by Name**, `Sites.Read.All` (OneDrive search runs on SharePoint search, which app-only tokens can only use with it), then click **Grant admin consent**. These reach every user's OneDrive in the tenant, so treat the client secret accordingly.
2. In Dify, add an authorization of the **API Key** type and fill in **Tenant ID** (your directory ID, not `common`), **Client ID**, **Client Secret**, **Default Drive Owner** (the user whose OneDrive to use, e.g. `alice@contoso.com`) and **Microsoft Cloud**. Dify signs in and opens that OneDrive to check the permission.
3. Each tool has an optional **Drive Owner** setting (set in the node, never chosen by the LLM) to use another user's OneDrive with the same credential.

The drive owner needs a license that includes OneDrive, and their OneDrive exists only after they have opened it once.

> **Known limitation — search with a Service Principal.** OneDrive search runs on SharePoint search. App-only tokens get `403 accessDenied` from it unless the app also has `Sites.Read.All`, and even with it Microsoft Graph may return an empty result for app-only requests (we saw this in our test tenant, for both drive search and the Microsoft Search API). Upload, Get File by ID and Delete File by ID are not affected. If you need search, use an OAuth authorization.

## Each user signs in (for chat agents, new in 1.0.0)

The first time a user needs OneDrive, the tool returns a Microsoft sign-in link instead of data; the agent passes it on, the user signs in in the browser, comes back and says they are done, and the agent calls the tool again. From then on the tools act on that user's own OneDrive, in later conversations too.

1. In the app registration, add the **Delegated** Microsoft Graph permissions `User.Read`, `Files.Read.All`, `Files.ReadWrite.All` and `offline_access` (search for `User.Read`, `Files.` and `offline`), and click **Grant admin consent** so users never see a consent screen.
2. In Dify, open the OneDrive plugin's details → **Endpoints**, click **+**, enter a name (nothing else to fill in), and copy the endpoint URL. It looks like `https://<your-dify-domain>/e/<id>/onedrive/callback`.
   If it starts with `http://localhost`, your self-hosted Dify still uses the default `ENDPOINT_URL_TEMPLATE=http://localhost/e/{hook_id}`: set `ENDPOINT_URL_TEMPLATE=https://<your-dify-domain>/e/{hook_id}` in `docker/.env` and restart the API (`docker compose up -d api`), or replace `http://localhost` with your Dify address by hand. Microsoft accepts `http` only for `localhost`.

   ![Endpoint URL](_assets/dify-endpoint-url.png)

3. In the app registration, open **Authentication** → **Add Redirect URI** → **Web**, paste the endpoint URL and click **Configure**. A mismatch shows up later as error `AADSTS50011` on the Microsoft sign-in page.

   ![Add redirect URI](_assets/entra-redirect-uri.png)

4. In Dify, click **Add API Key**, set **Mode** to *Each user signs in*, and fill in **Tenant ID**, **Client ID**, **Client Secret** (the secret's *Value*, not its Secret ID) and **Sign-in Callback URL**. Leave **Default Drive Owner** empty. On save, Dify checks the fields and, with a specific tenant ID, that Microsoft accepts the client ID and secret; no user's OneDrive is opened and no user token is stored in the authorization.

   ![Authorization form, top](_assets/dify-per-user-form-top.png)
   ![Authorization form, bottom: Default Drive Owner stays empty](_assets/dify-per-user-form-bottom.png)

5. In the agent, add **OneDrive**, keep the tools you want and **Sign Out of OneDrive**, and choose this authorization in the credential menu. If the menu shows an OAuth authorization instead, the tools use that one shared OneDrive and no one is asked to sign in. Instructions like these work well:

```
You can use the OneDrive tools on the current user's own OneDrive.
- If a tool says the user needs to sign in and returns a link, give the link to the user exactly as returned. Ask them to open it, sign in with their own Microsoft account, and reply "done" when finished. After they reply, call the same tool again.
- Before deleting a file, tell the user which file and ask them to confirm.
- Never make up files. If a tool returns an error, tell the user what it says.
- If the user asks to sign out or switch accounts, call onedrive_sign_out.
```

With Outlook and Teams in the same agent, each tool has its own per-user authorization:

![Outlook, Teams and OneDrive, each with its own per-user authorization](_assets/agent-credentials.png)

### What users see

A file attached in the chat is uploaded after the user signs in once; later requests (a download link, signing out) need no new sign-in until they sign out.

![Upload an attached file: sign-in link, then the upload](_assets/chat-upload-sign-in.png)

![Download link, then sign out](_assets/chat-download-sign-out.png)

Search works in this mode (it does not have the Service Principal limitation below): it runs as the user, with their delegated `Files.Read.All`.

How it works and what to know:
- Each user's tokens are kept in the plugin's storage, encrypted with a key derived from the client secret. They never reach the agent or the logs. The endpoint only holds a one-time authorization code briefly; turning it into a token also needs the client secret and a PKCE verifier it never sees.
- Users stay signed in while they keep using it (the access token is renewed hourly; Microsoft's refresh token expires after about 90 days unused). They sign in again after signing out, a password change, an administrator revoking their sessions, or a client secret rotation.
- Users are told apart by Dify's user ID. It is stable in the console and for Service API callers that always send the same `user`; in a public web app without login, each browser is a new anonymous user. The Service API `user` value is chosen by the caller, so call the API only from a trusted backend.
- Each plugin keeps its own sign-in: with Outlook or Teams in the same agent, a user signs in once for each, and signing out of one leaves the others signed in. With one app registration for all of them and admin consent, the later sign-ins usually need no password.
- A user could send their own sign-in link to a colleague, whose OneDrive would then be connected to the sender's chat. The **Signed in** page warns about this and offers to cancel; an administrator can end any connection by revoking the user's sessions in Entra.

## Tool Descriptions

### get_file_by_id
Retrieve a file or folder from OneDrive by its ID. For folders, `download` will not return as file.

**Parameters:**
- file_id (string): The ID of the file or folder to retrieve.
- download (boolean, optional): Whether to download the file or not.

### delete_file_by_id
Delete a file from OneDrive by its ID.

**Parameters:**
- file_id (string): The ID of the file to delete.

### search_file
Search for files or folders in OneDrive by name.

**Parameters:**
- query (string): The name of the file or folder to search for.
- limit (number, optional): The maximum number of results to return (default: 10).

### upload_file
Upload a file, or save text as a file, to the OneDrive root or a folder; a `file_name` such as `reports/q3.pdf` puts it in that folder.

**Parameters:**
- file (file, optional): The file to upload to OneDrive.
- file_name (string, optional): Name for the uploaded file. With a file, empty keeps the original name; required with `file_content`.
- file_content (string, optional, new in 1.0.0): Text to save as a UTF-8 file when no file is given, for example notes an agent was asked to save.
- parent_folder_id (string, optional, new in 1.0.0): ID of the folder to upload into; empty for the root.

### onedrive_list_folder (new in 1.0.0)
List the files and folders directly inside a folder, with their IDs.

**Parameters:**
- folder_id (string, optional): The folder to list; empty or `root` for the root folder.
- limit (number, optional): Maximum number of items, 1–200 (default 50).

### onedrive_create_folder (new in 1.0.0)
Create a folder. The name may be a path such as `Reports/2026`: missing folders along it are created and existing ones reused.

**Parameters:**
- name (string): Folder name or path.
- parent_folder_id (string, optional): The folder to create it in; empty for the root.

### onedrive_rename (new in 1.0.0)
Rename a file or folder.

**Parameters:**
- item_id (string): The file or folder.
- new_name (string): The new name, including the extension for a file.

### onedrive_copy (new in 1.0.0)
Copy a file or folder, into the same folder or another one, optionally under a new name; a name already taken gets a number appended. Small copies finish within the call; large ones continue in OneDrive and are reported as `in_progress`.

**Parameters:**
- file_id (string): The file or folder to copy.
- name (string, optional): Name of the copy.
- parent_folder_id (string, optional): Target folder; empty for the same folder, `root` for the root.

### onedrive_share (new in 1.0.0)
Create a sharing link for a file or folder.

**Parameters:**
- item_id (string): The file or folder.
- type (select, optional): `view` (default, read-only), `edit`, or `embed` (personal OneDrive only).
- scope (select, optional): `organization` (default, people in your organization) or `anonymous` (anyone with the link; administrators often turn these off).

With the existing tools, these five cover the common OneDrive operations (file: copy, delete, download, get, rename, search, share, upload; folder: create, delete, get children, rename, search, share). Their names carry an `onedrive_` prefix because Dify's agent requires tool names to be unique across all the plugins an agent uses.

### onedrive_sign_out
*Each user signs in* only: forget the current user's OneDrive sign-in, for switching accounts. Other plugins (for example Outlook) keep their own sign-in. No parameters.



## Output variables

Besides `text` and `json` (unchanged), every tool returns typed variables that later workflow nodes can pick directly, without parsing `json`. Every tool has `success` (boolean) and `error` (string, empty on success), so a workflow can branch with an IF node; list tools return an array of flat items plus `count`.

| Tool | Variables (besides `success`, `error`) |
|---|---|
| Get File or Folder by ID | `file_id`, `name`, `is_folder`, `mime_type`, `size`, `web_url`, `download_url`, `downloaded` |
| Delete File by ID | `file_id` |
| Search File or Folder by Name | `items`, `count` |
| Upload File | `file_id`, `name`, `size`, `web_url` |
| List Folder | `items`, `count`, `has_more` |
| Create Folder | `folder_id`, `name`, `web_url`, `created` |
| Rename File or Folder | `file_id`, `name`, `is_folder`, `web_url` |
| Copy File | `file_id`, `name`, `web_url`, `status` |
| Create Sharing Link | `link_url`, `type`, `scope`, `permission_id` |
| Sign Out of OneDrive | `signed_out` |

## PRIVACY

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

Last updated: October 22, 2026
