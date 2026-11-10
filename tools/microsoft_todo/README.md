# Microsoft To Do Plugin

**Author**: langgenius
**Version**: 1.0.0
**Type**: tool

## Introduction

This plugin integrates with Microsoft To Do through Microsoft Graph: read, create, update, complete and delete tasks and task lists, and link tasks to the items they came from in other apps. Version 1.0.0 covers all of these operations for tasks, lists and linked resources.

### Choose how to authorize

| Mode | Whose tasks the tools use | Use it for |
|---|---|---|
| **OAuth** | The one person who authorized from the Dify console; everyone using the tool shares that account | A workflow or app on one known account's tasks |
| **Service Principal** (new in 1.0.0) | A user you name, accessed as the app; nobody signs in | Automation, e.g. creating tasks for a team member from a workflow |
| **Each user signs in** (new in 1.0.0) | Whoever is chatting with the agent; each user signs in once with their own Microsoft account | A chat agent that many people use ("remind me to call Kim on Friday") |

All three use the same Microsoft Entra app registration and can exist side by side; pick one per agent or workflow node.

## Setup

1. Register your application in the [Microsoft Azure Portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).

<p align="center">
    <img src="_assets/azure_portal.png" alt="Azure Portal" width="400" />
</p>

2. Create a new application as follows:
    - **Name**: Dify To Do Plugin
    - **Supported account types**: for OAuth with personal accounts, select `Accounts in any organizational directory (Any Microsoft Entra ID tenant - Multitenant) and personal Microsoft accounts (e.g. Skype, Xbox)`; for your organization only (and for Service Principal or Each user signs in), *Single tenant* is enough.
    - **Redirect URI** (OAuth): choose `Web` and set the URI to:
        - For SaaS (cloud.dify.ai) users: `https://cloud.dify.ai/console/api/oauth/plugin/langgenius/microsoft_todo/microsoft_todo/tool/callback`
        - For self-hosted users: `https://<your CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/microsoft_todo/microsoft_todo/tool/callback`
        ***Microsoft only accepts redirect URIs that start with `https://` or `http://localhost`.***

<p align="center">
        <img src="_assets/register_app.png" alt="Azure Portal" width="500">
</p>

3. Copy your **Application (client) ID** (and, for Service Principal or Each user signs in, the **Directory (tenant) ID**).

<p align="center">
    <img src="_assets/client_id.png" alt="Azure Portal" width="600">
</p>

4. Create a new client secret and copy its **Value** (not the Secret ID; it is shown only once).

<p align="center">
    <img src="_assets/client_secret.png" alt="Azure Portal" width="600">
</p>

5. Under **API permissions** → **Add a permission** → **Microsoft Graph**, add:

    | Permission | Type | Search for | Needed by |
    |---|---|---|---|
    | `Tasks.ReadWrite` | Delegated | `Tasks` | OAuth, Each user signs in |
    | `offline_access`, `openid` | Delegated | `offline`, `openid` | OAuth, Each user signs in |
    | `User.Read` | Delegated | `User.Read` | Each user signs in (names the signed-in account; usually already there) |
    | `Tasks.ReadWrite.All` | Application | `Tasks` | Service Principal |

    Then click **Grant admin consent** (required for the application permission, and it spares users a consent screen).

6. Set up the mode you chose, below.

### OAuth

Click the settings icon next to **Add OAuth**, fill in **Client ID** and **Client Secret**, and optionally (new in 1.0.0) **Tenant ID** (default `common`, any work or personal account as before; your directory ID limits sign-in to your organization) and **Microsoft Cloud** (Global unless your tenant is in a national cloud). Make sure the redirect URI shown matches the one in Azure, then click **Save and authorize**.

<p align="center">
    <img src="_assets/setup.png" alt="Plugin Configuration" width="600">
</p>

Authorizations made with versions before 1.0.0 keep working; they move to the new credential format the next time their token is refreshed.

<p align="center">
    <img src="_assets/result-dify.png" alt="Plugin Configuration" width="45%">
    <img src="_assets/result-todo.png" alt="Plugin Configuration" width="45%">
</p>

### Service Principal (app-only, new in 1.0.0)

1. Give the app the **Application** permission `Tasks.ReadWrite.All` and grant admin consent. It reaches every user's tasks in the tenant, so treat the client secret accordingly.
2. Click **Add API Key**, keep **Mode** at *Service Principal*, and fill in **Tenant ID** (your directory ID, not `common`), **Client ID**, **Client Secret** and, optionally, **Default Task Owner** (e.g. `alice@contoso.com`). With a default task owner, Dify reads that user's lists to check the permission.
3. Each tool has a **Task Owner** setting (set in the node, never chosen by the LLM) to work on another user's tasks with the same credential.

To Do data lives in the user's Exchange Online mailbox, so the task owner needs one.

### Each user signs in (for chat agents, new in 1.0.0)

The first time a user needs To Do, the tool returns a Microsoft sign-in link instead of data; the agent passes it on, the user signs in in the browser, comes back and says they are done, and the agent calls the tool again. From then on the tools work on that user's own tasks, in later conversations too.

1. Give the app the **Delegated** permissions above and grant admin consent.
2. In Dify, open the plugin's details → **Endpoints**, click **+**, enter a name (nothing else to fill in), and copy the endpoint URL: `https://<your-dify-domain>/e/<id>/todo/callback`. If it starts with `http://localhost`, your self-hosted Dify still uses the default `ENDPOINT_URL_TEMPLATE=http://localhost/e/{hook_id}`: set `ENDPOINT_URL_TEMPLATE=https://<your-dify-domain>/e/{hook_id}` in `docker/.env` and restart the API, or replace `http://localhost` with your Dify address by hand.
3. In the app registration, open **Authentication** → **Add Redirect URI** → **Web**, paste the endpoint URL and click **Configure**. A mismatch shows up later as error `AADSTS50011` on the Microsoft sign-in page.
4. Click **Add API Key**, set **Mode** to *Each user signs in*, and fill in **Tenant ID**, **Client ID**, **Client Secret** and **Sign-in Callback URL**. Leave **Default Task Owner** empty.
5. In the agent, add the To Do tools you want and **Sign Out of To Do**, choose this authorization, and use instructions like:

   ```
   You can use the Microsoft To Do tools on the current user's own tasks.
   - Find lists with get_lists; read tasks with get_tasks_by_list_id or get_all_tasks (not completed ones unless asked).
   - If a tool says the user needs to sign in and returns a link, give the link to the user exactly as returned. Ask them to open it, sign in with their own Microsoft account, and reply "done" when finished. After they reply, call the same tool again.
   - Before deleting a list or a task, tell the user what will be deleted and ask them to confirm.
   - Never make up tasks. If a tool returns an error, tell the user what it says.
   - If the user asks to sign out or switch accounts, call todo_sign_out.
   ```

What to know:
- Each user's tokens are kept in the plugin's storage, encrypted with a key derived from the client secret. They never reach the agent or the logs. The endpoint only holds a one-time authorization code briefly; turning it into a token also needs the client secret and a PKCE verifier it never sees.
- Users stay signed in while they keep using it (the access token is renewed hourly; Microsoft's refresh token expires after about 90 days unused). They sign in again after signing out, a password change, an administrator revoking their sessions, or a client secret rotation.
- Users are told apart by Dify's user ID. It is stable in the console and for Service API callers that always send the same `user`; in a public web app without login, each browser is a new anonymous user. The Service API `user` value is chosen by the caller, so call the API only from a trusted backend.
- Each plugin keeps its own sign-in: with Outlook, Teams, OneDrive or Excel in the same agent, a user signs in once for each, and signing out of one leaves the others signed in.
- A user could send their own sign-in link to a colleague, whose account would then be connected to the sender's chat. The **Signed in** page warns about this and offers to cancel; an administrator can end any connection by revoking the user's sessions in Entra.

## Tool Descriptions

Every tool also has a **Task Owner** setting, used only with a Service Principal.

| Tool | Operation | What it does |
|---|---|---|
| `get_lists` | List: Get Many | The user's task lists |
| `get_tasks` | – | The user's task lists, like `get_lists` (the name is historical: it has always returned lists) |
| `get_list_by_id` | List: Get | One list (`list_id`) |
| `todo_create_list` | List: Create | A new list (`display_name`) |
| `todo_update_list` | List: Update | Rename a list (`list_id`, `display_name`) |
| `todo_delete_list` | List: Delete | Delete a list and its tasks |
| `get_tasks_by_list_id` | Task: Get Many | Tasks of a list; `status_filter`: `not_completed` (default, as before), `completed` or `all`; `limit` (default 1000) |
| `get_all_tasks` | – | Tasks of every list, with the same options; each task also carries its `list_id` and `list_name` |
| `get_task_by_id` | Task: Get | One task (`list_id`, `task_id`) |
| `create_task` | Task: Create | `title`, and optionally `due_date`, `body_text` (notes), `reminder_datetime`, `importance` (low / normal / high) and `status` (notStarted / inProgress / completed / waitingOnOthers / deferred) |
| `todo_update_task` | Task: Update | Change any of those fields; only the fields given change |
| `complete_task` | – | Mark a task completed |
| `todo_delete_task` | Task: Delete | Delete a task |
| `todo_list_linked_resources` | Linked Resource: Get Many | A task's links to the items it came from in other apps |
| `todo_get_linked_resource` | Linked Resource: Get | One linked resource |
| `todo_create_linked_resource` | Linked Resource: Create | `application_name` (required), `display_name`, `external_id`, `web_url` |
| `todo_update_linked_resource` | Linked Resource: Update | Change any of those fields |
| `todo_delete_linked_resource` | Linked Resource: Delete | Remove a linked resource |
| `todo_sign_out` | – | *Each user signs in* only: forget the current user's To Do sign-in |

Dates: `due_date` takes `YYYY-MM-DD` or an ISO 8601 date-time; `reminder_datetime` takes an ISO 8601 date-time. A value with a UTC offset is converted to UTC; one without is taken as UTC.

The new tools carry a `todo_` prefix because Dify's agent requires tool names to be unique across all the plugins an agent uses.

## Output variables (new in 1.0.0)

Besides `text` and `json` (unchanged), every tool returns typed variables that later workflow nodes can pick directly. Every tool has `success` (boolean) and `error` (string, empty on success).

| Tool | Variables (besides `success`, `error`) |
|---|---|
| get_lists, get_tasks | `lists`, `count` |
| get_list_by_id, todo_create_list, todo_update_list | `list_id`, `display_name` |
| todo_delete_list | `list_id` |
| get_tasks_by_list_id, get_all_tasks | `tasks`, `count` |
| get_task_by_id, create_task, todo_update_task, complete_task | `task_id`, `title`, `status`, `body_text`, `due_date`, `created_date`, `importance`, `reminder` |
| todo_delete_task | `task_id` |
| todo_list_linked_resources | `linked_resources`, `count` |
| todo_get_linked_resource, todo_create_linked_resource, todo_update_linked_resource | `linked_resource_id`, `display_name`, `application_name`, `external_id`, `web_url` |
| todo_delete_linked_resource | `linked_resource_id` |
| todo_sign_out | `signed_out` |

## PRIVACY

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

Last updated: November 1, 2026
