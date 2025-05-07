# Smartsheet Plugin for Dify

**Author:** langgenius
**Version:** 0.0.1
**Type:** Tool Plugin

## Description
The Smartsheet Plugin for Dify enables you to interact with Smartsheet data directly from your Dify AI applications. Access and manage Smartsheet sheets programmatically to enhance your AI workflows.

## Features
- **Get Sheet Info**: Retrieve detailed sheet information including columns and sample data
- **Add Rows**: Add new rows to a Smartsheet with specified values
- **Update Rows**: Update existing rows in a Smartsheet with new values
- **Search Sheet**: Search for data within a Smartsheet

## Installation
1. In your Dify workspace, navigate to the Plugin section
2. Search for "Smartsheet" and install the plugin
3. Enter your Smartsheet API key when prompted

## Configuration
You will need a Smartsheet API key to use this plugin:
1. Log in to your Smartsheet account
2. Go to Account > Personal Settings > API Access
3. Generate a new access token
4. Copy and paste this token into the plugin configuration

## Usage Examples

### Get Sheet Information
```
Get information about my Smartsheet with ID 123456789
```

```
What columns are available in Smartsheet sheet 987654321?
```

### Add Rows
```
Add a row to Smartsheet 123456789 with Project Name "New Project", Status "In Progress", and Due Date "2023-12-31"
```

```
Add these two rows to my Smartsheet 987654321:
- Task: "Complete documentation", Status: "Not Started", Assignee: "John"
- Task: "Review code", Status: "In Progress", Assignee: "Sarah"
```

### Update Rows
```
Update row 234567890 in Smartsheet 123456789 to change Status to "Completed"
```

```
In Smartsheet 987654321, update row 345678901 to set Priority to "High" and Due Date to "2023-11-15"
```

### Search Sheet
```
Search Smartsheet 123456789 for "quarterly report"
```

```
Find all rows in Smartsheet 987654321 that contain "urgent"
```

## Troubleshooting
If you encounter issues with the plugin:
- Verify your API key is correct and has the necessary permissions
- Check that the sheet ID is valid and accessible with your account
- Ensure your Smartsheet API access is enabled
- For row operations, confirm that the column names match exactly with those in your sheet

## Contributing
Interested in contributing to this plugin? Please contact the Dify team for more information.

## License
This plugin is released under the MIT License.



