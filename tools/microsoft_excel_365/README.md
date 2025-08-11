# Microsoft Excel 365 Dify Plugin

This Dify plugin provides integration with Microsoft Excel 365 through OAuth authentication, enabling spreadsheet operations via Microsoft Graph API.

## Features

The plugin supports the following Excel operations:

### 📊 Workbook Operations
- **List Workbooks**: Browse all Excel workbooks in OneDrive/SharePoint
- **Search Workbooks**: Filter workbooks by name or folder

### 📋 Worksheet Operations  
- **List Worksheets**: Get all worksheets in a workbook
- **Create Worksheet**: Add new worksheets to existing workbooks
- **Read Data**: Read cell values from specified ranges
- **Write Data**: Update or insert data into cells
- **Clear Data**: Remove content from cell ranges
- **Search Data**: Find specific values within worksheets

## Setup Instructions

### 1. Azure App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to "App registrations" 
3. Click "New registration"
4. Configure your app:
   - Name: Your app name (e.g., "Dify Excel Plugin")
   - Supported account types: Choose based on your needs
   - Redirect URI: Add `https://your-dify-instance.com/api/oauth/callback/excel365`
5. After creation, note down:
   - **Application (client) ID**
   - Go to "Certificates & secrets" → "New client secret" → Copy the **Value**

### 2. Configure API Permissions

In your Azure app registration:
1. Go to "API permissions"
2. Click "Add a permission" → "Microsoft Graph"
3. Add the following permissions:
   - `Files.ReadWrite` (Delegated)
   - `offline_access` (Delegated)
4. Grant admin consent if required

### 3. Install in Dify

1. Upload this plugin to your Dify instance
2. Configure OAuth credentials:
   - Client ID: Your Azure app's Application ID
   - Client Secret: Your Azure app's client secret
3. Authenticate with your Microsoft account
4. Start using the Excel tools!

## Scopes (Hard-coded)

The plugin uses the following Microsoft Graph scopes (hard-coded in the provider):
- `Files.ReadWrite`: Read and write user's files
- `offline_access`: Maintain access to data you have given it access to

## Tool Usage Examples

### List all Excel workbooks
```
Tool: list_workbooks
Parameters:
  - folder_id: (optional)
  - search_query: (optional)
  - max_results: 20
```

### Read data from a worksheet
```
Tool: read_worksheet_data
Parameters:
  - workbook_id: "ABC123..."
  - worksheet_name: "Sheet1"
  - range: "A1:D10"
```

### Write data to cells
```
Tool: write_worksheet_data
Parameters:
  - workbook_id: "ABC123..."
  - worksheet_name: "Sheet1"  
  - range: "A1:B2"
  - values: [["Header1", "Header2"], ["Value1", "Value2"]]
```

### Search for values
```
Tool: search_worksheet_data
Parameters:
  - workbook_id: "ABC123..."
  - worksheet_name: "Sheet1"
  - search_value: "Revenue"
  - range: "A1:Z1000"
```

## Important Notes

- The plugin requires active Microsoft 365 subscription with Excel access
- Files must be stored in OneDrive or SharePoint
- Large ranges may impact performance - use specific ranges when possible
- The OAuth token auto-refreshes using the refresh token

## Troubleshooting

### Authentication Issues
- Ensure redirect URI matches exactly in Azure app settings
- Check that all required permissions are granted
- Try re-authenticating if token expires

### Access Issues  
- Verify the user has access to the target workbooks
- Ensure files are in OneDrive/SharePoint (not local)
- Check file isn't locked by another user

### Data Format Issues
- Values must be provided as 2D arrays for write operations
- Use proper Excel A1 notation for ranges (e.g., "A1:D10")
- Worksheet names are case-sensitive

## Support

For issues or questions:
- Check Azure app configuration
- Verify Microsoft Graph API status
- Review Dify plugin logs for detailed error messages

## License

This plugin is provided as-is for use with Dify platform.