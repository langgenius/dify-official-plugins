# Notion Plugin for Dify

## Overview

The Notion Plugin for Dify provides integration with Notion workspaces, allowing you to search, query databases, create and update pages directly from your Dify applications. It enables seamless interaction with your Notion content without leaving your Dify environment.

## Features

- **Search Notion**: Search for pages and databases in your Notion workspace by keywords
- **Query Database**: Retrieve and filter content from specific Notion databases
- **Create Page**: Create new pages in your Notion workspace with custom title and content
- **Retrieve Page**: Get a specific page and its content by ID
- **Update Page**: Update an existing page's title or add new content
- **Retrieve Database**: Get database structure and schema information
- **Create Database**: Create a new database with custom properties and schema
- **Update Database**: Modify an existing database's title or properties
- **Update Database Record**: Update property values of an existing record (row) in a database
- **Retrieve Comments**: Get comments from a specific page or block
- **Create Comment**: Add a new comment to a Notion page

## Configuration

### 1. Setting up Integration in Notion

Go to [Notion Integrations](https://www.notion.so/my-integrations) and create a new **internal** integration or select an existing one.

![](_assets/docs/integrations-creation.png)

Give your integration an appropriate name and select the workspace you want to connect it to.

For security reasons, you may want to limit the capabilities of your integration. For example, you can create a read-only integration by only enabling "Read content" permission:

![](_assets/docs/integrations-capabilities.png)

Copy your "Internal Integration Secret" from the "Secrets" tab. You'll need this to configure the plugin in Dify.

**Important:** Keep this secret secure. Anyone with this token can access content shared with your integration.

### 2. Connecting Content to Your Integration

For your integration to access specific pages or databases, you must explicitly share them with your integration:

1. Navigate to the page or database you want to access through the plugin
2. Click the "•••" (three dots) menu in the top-right corner
3. Select "Add connections" and choose your integration from the list

![](_assets/docs/connections.png)

Repeat this process for each page or database you want to access with the plugin.

### 3. Configuring the Plugin in Dify

1. In your Dify workspace, navigate to the Plugins section
2. Find and select the Notion plugin
3. Paste your Integration Secret in the configuration field
4. Save your configuration

## Usage Examples

### Search Notion
```
Find pages in my Notion workspace containing "project plan"
```

### Query a Database
```
Show me all items in my Notion database with ID "abc123" where Status is "In Progress"
```

By default, `query_database` returns up to `limit` records (default 10). To retrieve every matching record in the database, set `fetch_all: true`, which automatically paginates through Notion's API. Each API call returns up to 100 records, and pagination is bounded by `max_api_calls` (default 500, so ~50,000 records max by default). The response includes `fetch_truncated: true` if the cap was hit. When `fetch_all` is enabled, the `limit` parameter is ignored. For large databases, consider tuning `max_api_calls` based on your expected record count to balance completeness with latency.

### Create a Page
```
Create a new Notion page titled "Meeting Notes" with content "Discussed project timeline and assigned tasks."
```

### Retrieve a Page
```
Get the Notion page with ID "abc123" and include its content
```

`retrieve_page` fetches every block on the page, paginating `blocks.children.list`
and recursing into blocks with `has_children` (toggles, callouts, quotes, bulleted /
numbered list items, columns, etc.). It does **not** descend into `child_page` /
`child_database` blocks — those are separate resources and should be fetched
separately. Recursion is bounded by `max_depth` (default 5) and total Notion API
calls are capped by `max_api_calls` (default 500). The response includes
`api_calls_made`, `total_blocks_fetched`, and `elapsed_seconds`, plus
`fetch_truncated: true` if the cap was hit. Large or deeply-nested pages can take
several seconds; tune `max_depth` / `max_api_calls` for latency-sensitive contexts.

### Update a Page
```
Update the title of Notion page "abc123" to "Updated Meeting Notes" and add "Follow-up scheduled for next week" to the content
```

### Retrieve Database Structure
```
Get the structure and properties of Notion database "abc123"
```

### Create Database
```
Create a new database in Notion page "abc123" titled "Project Tasks" with properties for Name (title), Status (select), and Due Date (date)
```

### Update Database
```
Update the Notion database "abc123" to rename the "Status" property to "Progress"
```

### Update a Database Record
```
In Notion database "abc123", set Name to "D" for the record whose No is 2
```

`update_database_record` finds the record either by `page_id` or by `database_id` + `match_property` + `match_value`, and takes the new values as a simple JSON object such as `{"Name": "D", "Status": "Done"}`. Each value is converted to the Notion format for that property's type.

- Matching is an exact match. `match_property` supports title, text, number, unique ID (`2` or `TASK-2`), select, status, checkbox, date, URL, email and phone properties. Only the database's first data source is searched.
- If more than one record matches, nothing is updated and up to 10 candidates are returned. Enable `update_all_matches` (a node setting) to update every match, up to `max_updates` (default 10, max 1000); if more records match, nothing is updated.
- List values (multi-select, people, relation, files) replace the current value rather than adding to it. `null` or `""` clears a value, except for the title (cannot be cleared) and checkboxes (send `false`). People values must be user IDs; `query_database` returns people as names, so send the complete list of IDs to keep.
- The JSON result has a `status` of `updated`, `partially_updated`, `not_found` (no record matches), `not_accessible` (the database or page is not shared with the integration), `ambiguous`, `too_many_matches`, `invalid_input` or `error`, so later workflow nodes can branch on it.
- The integration needs the **Update content** capability.

Note that `update_database` changes the database schema (property definitions), not record values.

### Retrieve Comments
```
Get all comments from the Notion page "abc123"
```

### Create Comment
```
Add a comment "Great progress on this task!" to Notion page "abc123"
```

## Supported Operations

1. **Search**: Find pages and databases across your workspace
2. **Query Database**: Retrieve and filter records from a specific database
3. **Create Page**: Create new pages with title and content
4. **Retrieve Page**: Get page details including properties and content blocks
5. **Update Page**: Modify page titles or append new content 
6. **Retrieve Database**: Get database structure, schema and property types
7. **Create Database**: Create new databases with custom properties
8. **Update Database**: Update database title or modify properties
9. **Update Database Record**: Update property values of existing records
10. **Retrieve Comments**: Get comments from a page or block
11. **Create Comment**: Add comments to a page
12. **Extract Data**: Process various Notion property types including rich text, select, multi-select, etc.

## Troubleshooting

- **Authentication Errors**: Make sure your integration token is valid and not expired
- **Access Errors**: Ensure the integration has been given access to the pages/databases you're trying to work with
- **Not Found Errors**: Check that the database or page IDs are correct and accessible
- **Rate Limiting**: If you receive rate limit errors, the plugin will automatically retry with backoff
