# Google Docs

Read, create and edit Google Docs from Dify workflows and agents. Content goes in and comes out as Markdown, so agents can write formatted documents and read them back.

## Tools

| Tool | What it does |
|---|---|
| `google_docs_find_documents` | Find documents by name (most recent first, including shared drives) |
| `google_docs_get_document` | A document as Markdown: headings, bullet and numbered lists, tables, bold/italic, links. Also returns its title and headings |
| `google_docs_create_document` | Create a document, optionally with Markdown content |
| `google_docs_append_content` | Add Markdown content at the end (optionally on a new page) or at the start |
| `google_docs_replace_text` | Replace every occurrence of a text, or several at once (`{"{{name}}": "Kim"}`). Replacing with nothing deletes the text |
| `google_docs_insert_table` | Add a table at the end, filled from a JSON grid (header row bold) |
| `google_docs_sign_out` | Each user signs in only: forget the current user's sign-in |

**Markdown the writer understands**:
- `#`, `##`, `###` headings;
- `-` or `*` bullet lists and `1.` numbered lists;
- `**bold**`, `*italic*` and `[text](https://link)`.

Everything else becomes normal paragraphs.

**Filling a template**: copy the template document in Drive (for example with the Google Drive plugin), then use `google_docs_replace_text` on the copy.

More details:
- **Document IDs**: tools accept a document's ID or its URL.
- **Output variables**: every tool returns typed output variables (`success` / `error` plus its fields) for workflows.

## Setup

You need a Google OAuth client:

1. **Create a project**: in the [Google Cloud Console](https://console.cloud.google.com/), create a project (or use an existing one).
2. **Enable the APIs**: open **APIs & Services › Library** and enable the **Google Docs API** and the **Google Drive API**. Drive is only used to find documents by name.
3. **Configure Google Auth Platform**:
   - **Branding**: app name and support email.
   - **Audience**: *Internal* for your Google Workspace organization, or *External*. While an External app is in *Testing*, add the people who will sign in as **Test users**.
4. **Create a client**: under **Clients**, create one of type **Web application**. Add the redirect URIs from the modes you use (below), then **Save**, and copy the **Client ID** and **Client Secret**. New redirect URIs can take a few minutes to apply.

**Permissions** the plugin asks for:
- `documents`: read and write documents.
- `drive.metadata.readonly`: find documents by name.

`drive.metadata.readonly` is a *restricted* scope: an External app published for users outside your organization must pass Google's verification. Internal apps and apps in Testing don't need it.

### OAuth (one shared account)

1. In Dify, open the plugin's authorization and choose **OAuth**. Add Dify's redirect URL to the client: `https://<your-dify>/console/api/oauth/plugin/langgenius/google_docs/google_docs/tool/callback`.
2. Enter the **Client ID** and **Client Secret**, then authorize with the Google account the plugin should use.

### Each user signs in (for chat agents)

Every chat user signs in with their own Google account, and the tools work on that person's documents.

1. **Create the sign-in endpoint**: open the plugin's details › **Endpoints** and create an endpoint (no settings). Copy its URL ending in `/google_docs/callback`.
   - If the URL starts with `http://localhost`, set `ENDPOINT_URL_TEMPLATE` on the Dify API service to your public address, e.g. `https://dify.example.com/e/{hook_id}`.
   - Google only accepts `https://` redirect URIs, except for `localhost`.
2. **Register the URL with Google**: add it to the client's **Authorized redirect URIs** and save. One client can serve several Google plugins.
3. **Add a credential in Dify**: in the plugin's authorization, add an API-key style credential with:
   - **Mode**: *Each user signs in*.
   - **Client ID** and **Client Secret**.
   - **Sign-in Callback URL**: the endpoint URL.
4. **Use it in an agent**: add the Google Docs tools to a chat agent with this credential.

**What users see**:
1. The agent replies with a Google sign-in link.
2. The user picks their account and allows access. They must keep both boxes ticked; if a permission is unticked, the plugin asks them to sign in again.
3. The page shows *Signed in*. Back in the chat, the user says they are done.
4. The agent continues and says which account was signed in.

While the app is in *Testing*, Google first shows "Google hasn't verified this app"; click **Continue**.

**Good to know**:
- **Signing out**: asking the agent to sign out of Google Docs (`google_docs_sign_out`) forgets that user's sign-in. Other Google plugins keep their own sign-ins.
- **Signing in again**: users are asked to sign in again when they revoke access or when the Client Secret changes. While the app is in **Testing**, Google expires refresh tokens after 7 days.
- **Security**:
  - The endpoint only stores the one-time authorization code. The tool redeems it with the client secret and a PKCE verifier.
  - Per-user tokens are encrypted with a key derived from the Client Secret and never appear in tool output.
  - Document IDs are URL-encoded.

## Troubleshooting

| Message | Fix |
|---|---|
| `Error 403: access_denied` when signing in | The app is in Testing and this account is not a test user. Add it under Google Auth Platform › Audience › **Test users**. |
| `Error 400: redirect_uri_mismatch` | Add the exact endpoint URL (or Dify's OAuth redirect URL) to the client's Authorized redirect URIs, click **Save**, and allow a few minutes. |
| `Google Docs API error 403` mentioning the API | Enable the Google Docs API (and the Google Drive API for finding documents) in the client's project. |

## Privacy

See [PRIVACY.md](PRIVACY.md).
