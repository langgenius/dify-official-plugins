# HubSpot Plugin for Dify

Integrate HubSpot CRM with Dify — manage contacts, companies, deals, tickets, engagements, lists and forms directly from your workflows and agents. Every list/search tool supports **filtering and sorting** so large result sets stay manageable.

## Tools

**Contacts** — Create, Update, Delete, Get, **Search**
**Companies** — Create, Update, Delete, Get, **Search**
**Deals** — Create, Update, Delete, Get, **Search**
**Tickets** — Create, Update, Delete, Get, **Search**
**Engagements** (notes / tasks / meetings / calls / emails) — Create, Get, **Search**, Delete
**Contact Lists** — Add contacts to a list, Remove contacts from a list
**Forms** — Get form (fields), Submit form

### Filtering & sorting (Search tools)

Each `search_*` tool exposes:
- `query` — full-text search
- `filter_property` + `filter_operator` (EQ, NEQ, GT/GTE, LT/LTE, CONTAINS_TOKEN, HAS_PROPERTY, …) + `filter_value`
- `sort_by` + `sort_direction` (ASCENDING / DESCENDING)
- `properties` (which fields to return), `limit` (1–100), `after` (pagination cursor)

Leave everything empty to list recent records; add a filter/sort to narrow and order results. These map to HubSpot's CRM Search API.

## Authentication

Create a **HubSpot Private App** and copy its access token:

1. HubSpot → Settings → Integrations → **Private Apps** → *Create a private app*.
2. Under **Scopes**, grant the CRM read/write scopes you need, e.g.:
   - `crm.objects.contacts.read` / `.write`
   - `crm.objects.companies.read` / `.write`
   - `crm.objects.deals.read` / `.write`
   - `crm.objects.tickets.read` / `.write`
   - (lists/forms as needed)
3. Create the app and copy the **access token**.
4. In Dify, paste it into the plugin's **API Access Token** field.

Keep the token secret; it grants access to your HubSpot data.

### Or: OAuth 2.0

The plugin also supports OAuth 2.0 (for multi-account / public-app use). In Dify, choose the OAuth option and provide your HubSpot app's **Client ID** and **Client Secret** (and optionally a custom scope string), then authorize. Tokens are refreshed automatically. Use the Private App token for a single account; use OAuth to let multiple HubSpot accounts connect.

## Notes

- Search results are capped at 100 per call — use `after` (the returned `paging.next.after`) to page through more.
- `submit_form` uses the HubSpot Forms submission API and takes your `portal_id` and `form_guid` (no token needed for that endpoint).
- Engagements are separate CRM object types — pick the type (note/task/meeting/call/email) on those tools.

## Privacy

See [PRIVACY.md](PRIVACY.md).
