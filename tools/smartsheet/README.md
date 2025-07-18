# Smartsheet Plugin for Dify

This plugin integrates Smartsheet's work management capabilities with Dify, allowing you to view, create, update, and search data in your Smartsheet sheets directly from your Dify applications.

## Features

- **Get Sheet Info**: Retrieve detailed information about a Smartsheet sheet, including columns, metadata, and sample data.
- **Add Rows**: Add one or more new rows to a Smartsheet with custom column values.
- **Update Rows**: Modify existing rows in a Smartsheet by updating specific cells.
- **Search Sheet**: Search for data within a Smartsheet using text-based search terms.

## Installation

1. Install the plugin through Dify's Plugin Marketplace.
2. Configure the plugin with your Smartsheet API key.

## Authentication

You'll need a **Smartsheet API key** to use this plugin:

1. Log in to [Smartsheet](https://app.smartsheet.com)
2. Go to Account → Personal Settings → API Access
3. Generate a new access token
4. Copy the generated token immediately (it won't be shown again)
5. Paste the token into the **Smartsheet API Key** field in the plugin configuration

**Important**: Your API key grants full access to your Smartsheet account. Keep it secure and never share it publicly.

## Usage

The plugin provides the following tools that can be used in your Dify applications:

### Get Sheet Info

Retrieves detailed information about a specified Smartsheet sheet, including column definitions, column types, and a sample of data rows.

Required parameters:
- `sheet_id`: The unique identifier of the Smartsheet sheet to retrieve information about. This is a number that appears in the URL when viewing the sheet in a web browser (e.g., https://app.smartsheet.com/sheets/SHEET_ID).

Example:
```
Get information about my Smartsheet with ID 123456789
```

### Add Rows

Adds one or more rows to a specified Smartsheet sheet with custom column values.

Required parameters:
- `sheet_id`: The unique identifier of the Smartsheet sheet to add rows to.
- `row_data`: The data for the rows to be added, formatted as a JSON array of objects where each object maps column names to values.

Optional parameters:
- `to_top`: String value that should be "true" to add rows to the top of the sheet or "false" to add to the bottom. Defaults to "true".

Example:
```
Add a row to Smartsheet 123456789 with Project Name "New Project", Status "In Progress", and Due Date "2023-12-31"
```

### Update Rows

Updates existing rows in a specified Smartsheet sheet by modifying specific cell values.

Required parameters:
- `sheet_id`: The unique identifier of the Smartsheet sheet containing the rows to update.
- `row_updates`: The data for updating rows, formatted as a JSON array of objects where each object includes a row_id and the column values to update.

Example:
```
Update row 234567890 in Smartsheet 123456789 to change Status to "Completed"
```

### Search Sheet

Searches for data within a specified Smartsheet sheet using a text-based search term.

Required parameters:
- `sheet_id`: The unique identifier of the Smartsheet sheet to search in.
- `search_term`: The text to search for within the sheet (case-insensitive, matches partial text).

Optional parameters:
- `max_results`: The maximum number of matching rows to return. Defaults to 10.

Example:
```
Search Smartsheet 123456789 for "quarterly report"
```

## Troubleshooting

If you encounter issues with the plugin:
- Verify your API key is correct and has the necessary permissions
- Check that the sheet ID is valid and accessible with your account
- Ensure your Smartsheet API access is enabled
- For row operations, confirm that the column names match exactly with those in your sheet

## License

This plugin is released under the MIT License.



