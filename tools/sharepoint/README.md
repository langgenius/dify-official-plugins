# Microsoft SharePoint

**Author**: langgenius
**Version**: 1.0.0
**Type**: tool

## Overview

Read and write SharePoint **lists**, **list items** and **document library files** through Microsoft Graph, from workflows and agents. The tools cover every operation of n8n's Microsoft SharePoint node, plus the lookups an agent needs to find sites, lists and files by itself.

To search content across all of SharePoint and OneDrive, or to import documents into a knowledge base, use the **SharePoint datasource** plugin instead; this plugin works on lists and files you point it at.

### Choose how to authorize

| Mode | Acts as | Use it for |
|---|---|---|
| **OAuth** | The one person who authorized from the Dify console; everyone using the tool shares their access | A workflow or app with one known account |
| **Service Principal** | The app itself; nobody signs in | Automation, e.g. a workflow that files every new request into a list |
| **Each user signs in** | Whoever is chatting with the agent, with their own SharePoint permissions; each user signs in once | A chat agent that many people use ("add this to our team's tracker") |

All three use the same Microsoft Entra app registration and can exist side by side; pick one per agent or workflow node.

## Setup

### 1. Register an app in Microsoft Entra ID

1. In the [Microsoft Entra admin center](https://entra.microsoft.com) → **App registrations** → **New registration**, enter a name (e.g. `Dify SharePoint`), keep **Single tenant only**, and register.
2. On the app's **Overview**, copy the **Application (client) ID** and the **Directory (tenant) ID**.
3. Under **Certificates & secrets** → **New client secret**, copy the secret's **Value** right away (it is shown once; the Secret ID is not the secret).
4. Under **API permissions** → **Add a permission** → **Microsoft Graph**, add:

   | Permission | Type | Search for | Needed by |
   |---|---|---|---|
   | `Sites.ReadWrite.All` | Delegated | `Sites.` | OAuth, Each user signs in |
   | `User.Read`, `offline_access` | Delegated | `User.Read`, `offline` | OAuth, Each user signs in |
   | `Sites.ReadWrite.All` (or `Sites.Selected`) | Application | `Sites.` | Service Principal |

   Then click **Grant admin consent**. `Sites.ReadWrite.All` (application) reaches every site in the tenant; to limit the app to some sites, use `Sites.Selected` instead and grant the app access to each site ([how](https://learn.microsoft.com/graph/permissions-selected-overview)).

### 2a. OAuth

Click the settings icon next to **Add OAuth**, fill in **Client ID**, **Client Secret**, and optionally **Tenant ID** (default `common`) and **Microsoft Cloud** (Global unless your tenant is in a national cloud). Add the redirect URI shown there to the app registration (**Authentication** → **Add Redirect URI** → **Web**), then click **Save and authorize**.

### 2b. Service Principal

Click **Add API Key**, keep **Mode** at *Service Principal*, and fill in **Tenant ID** (your directory ID, not `common`), **Client ID** and **Client Secret**. Dify signs in as the app and reads the root site to check the permission (with `Sites.Selected`, grant the root site too, or the check fails).

### 2c. Each user signs in (for chat agents)

The first time a user needs SharePoint, the tool returns a Microsoft sign-in link instead of data; the agent passes it on, the user signs in in the browser, comes back and says they are done, and the agent calls the tool again. From then on the tools act as that user, with their own SharePoint permissions, in later conversations too.

1. In Dify, open the plugin's details → **Endpoints**, click **+**, enter a name (nothing else to fill in), and copy the endpoint URL: `https://<your-dify-domain>/e/<id>/sharepoint/callback`. If it starts with `http://localhost`, your self-hosted Dify still uses the default `ENDPOINT_URL_TEMPLATE=http://localhost/e/{hook_id}`: set `ENDPOINT_URL_TEMPLATE=https://<your-dify-domain>/e/{hook_id}` in `docker/.env` and restart the API, or replace `http://localhost` with your Dify address by hand.
2. In the app registration, open **Authentication** → **Add Redirect URI** → **Web**, paste the endpoint URL and click **Configure**. A mismatch shows up later as error `AADSTS50011` on the Microsoft sign-in page.
3. Click **Add API Key**, set **Mode** to *Each user signs in*, and fill in **Tenant ID**, **Client ID**, **Client Secret** and **Sign-in Callback URL**.
4. In the agent, add the SharePoint tools you want and **Sign Out of SharePoint**, choose this authorization, and use instructions like:

   ```
   You can use the SharePoint tools on behalf of the current user.
   - Find a site with sharepoint_search_sites or sharepoint_get_site (a site URL works), its lists with sharepoint_list_lists, and a list's column names with sharepoint_get_list before writing items.
   - If a tool says the user needs to sign in and returns a link, give the link to the user exactly as returned. Ask them to open it, sign in with their own Microsoft account, and reply "done" when finished. After they reply, call the same tool again.
   - Before deleting an item or replacing a file, tell the user what will change and ask them to confirm.
   - Never make up data. If a tool returns an error, tell the user what it says.
   - If the user asks to sign out or switch accounts, call sharepoint_sign_out.
   ```

What to know:
- Each user's tokens are kept in the plugin's storage, encrypted with a key derived from the client secret. They never reach the agent or the logs. The endpoint only holds a one-time authorization code briefly; turning it into a token also needs the client secret and a PKCE verifier it never sees.
- Users stay signed in while they keep using it (the access token is renewed hourly; Microsoft's refresh token expires after about 90 days unused). They sign in again after signing out, a password change, an administrator revoking their sessions, or a client secret rotation.
- Users are told apart by Dify's user ID. It is stable in the console and for Service API callers that always send the same `user`; in a public web app without login, each browser is a new anonymous user. The Service API `user` value is chosen by the caller, so call the API only from a trusted backend.
- Each plugin keeps its own sign-in: with Outlook, Teams, OneDrive, Excel or To Do in the same agent, a user signs in once for each, and signing out of one leaves the others signed in.
- A user could send their own sign-in link to a colleague, whose account would then be connected to the sender's chat. The **Signed in** page warns about this and offers to cancel; an administrator can end any connection by revoking the user's sessions in Entra.

## Tools

Every tool takes a **Site**: its URL (`https://contoso.sharepoint.com/sites/Team`, a link to a page or file in the site works too), its ID from **Search Sites**, or `root`. Lists are named by ID or name; files and folders by ID (from **List Files**). Files are in the site's default document library.

| Tool | n8n operation | What it does |
|---|---|---|
| `sharepoint_search_sites` | (site picker) | Find sites by name |
| `sharepoint_get_site` | (site picker) | A site from its URL, ID or `root` |
| `sharepoint_list_lists` | List: Get Many | Lists and document libraries of a site (hidden system lists only on request) |
| `sharepoint_get_list` | List: Get | A list and its columns: internal names, types, required, choices |
| `sharepoint_list_items` | Item: Get Many | Items with their fields; optional OData `filter` such as `fields/Status eq 'Done'` (allowed on non-indexed columns), `limit` up to 5000 |
| `sharepoint_get_item` | Item: Get | One item |
| `sharepoint_create_item` | Item: Create | Add an item from a JSON object of column values |
| `sharepoint_update_item` | Item: Update | Change some columns of an item |
| `sharepoint_upsert_item` | Item: Create or Update | Update the item whose `match_columns` equal the given values, or create it; more than one match is an error |
| `sharepoint_delete_item` | Item: Delete | Delete an item (to the recycle bin) |
| `sharepoint_list_files` | (folder and file pickers) | Files and folders in a folder of the document library |
| `sharepoint_download_file` | File: Download | Download a file (up to 15 MB) |
| `sharepoint_upload_file` | File: Upload | Upload a file, or save text as a file, into a folder; same name replaces |
| `sharepoint_update_file` | File: Update | Rename a file and/or replace its content |
| `sharepoint_sign_out` | – | *Each user signs in* only: forget the current user's SharePoint sign-in |

Column values use the columns' **internal** names (e.g. `Title`, `Status`, `Due_x0020_Date`); `sharepoint_get_list` shows them. Item fields are returned without SharePoint's system columns.

## Output variables

Besides `text` and `json`, every tool returns typed variables that later workflow nodes can pick directly; every tool has `success` (boolean) and `error` (string, empty on success).

| Tool | Variables (besides `success`, `error`) |
|---|---|
| sharepoint_search_sites | `sites`, `count` |
| sharepoint_get_site | `site_id`, `name`, `web_url`, `description` |
| sharepoint_list_lists | `lists`, `count`, `site_id` |
| sharepoint_get_list | `list_id`, `name`, `description`, `template`, `web_url`, `hidden`, `columns` |
| sharepoint_list_items | `items`, `count` |
| sharepoint_get_item, sharepoint_create_item | `item_id`, `fields`, `web_url`, `created`, `modified` |
| sharepoint_update_item | `item_id`, `updated_fields` |
| sharepoint_upsert_item | `item_id`, `action` (`created` or `updated`) |
| sharepoint_delete_item | `item_id` |
| sharepoint_list_files | `files`, `count` |
| sharepoint_download_file | `name`, `size`, `mime_type`, `web_url`, `downloaded` |
| sharepoint_upload_file, sharepoint_update_file | `file_id`, `name`, `size`, `web_url` |
| sharepoint_sign_out | `signed_out` |

## Privacy

See [PRIVACY.md](PRIVACY.md).
