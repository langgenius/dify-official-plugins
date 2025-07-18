# NocoDB Plugin for Dify

This plugin integrates NocoDB's database management capabilities with Dify, allowing you to create, retrieve, update, and delete records in your NocoDB databases directly from your Dify applications.

## Features

- **Retrieve Records**: Query records from NocoDB tables with filtering, sorting, and pagination support
- **Create Records**: Insert new records into tables with single or bulk operations
- **Update Records**: Modify existing records by ID or perform bulk updates across multiple records
- **Delete Records**: Remove records from tables with single or bulk deletion operations
- **Get Table Schema**: Retrieve complete table structure including column definitions, data types, and constraints
- **Flexible Filtering**: Support for NocoDB's powerful query syntax for complex data retrieval
- **Bulk Operations**: Efficient handling of multiple records in single API calls
- **Authentication**: Secure connection using NocoDB API tokens

## Installation

1. Install the plugin through Dify's Plugin Marketplace.
2. Configure the plugin with your NocoDB credentials.

## Authentication

You'll need the following credentials to use this plugin:

### NocoDB URL
The base URL of your NocoDB instance (e.g., `https://your-nocodb.com` or `http://localhost:8080` for local installations).

### NocoDB API Token
You'll need a **NocoDB API Token** to authenticate:

1. Log in to your NocoDB instance
2. Go to your account settings (click your profile picture in the top right)
3. Navigate to **Account Settings > API Tokens**
4. Click **Generate Token** or **Create New Token**
5. Give your token a descriptive name (e.g., "Dify Integration")
6. Copy the generated token immediately (it may not be shown again)
7. Paste the token into the **NocoDB API Token** field in the plugin configuration

### NocoDB Base ID
The ID of the specific NocoDB base/project you want to work with:

1. Open your NocoDB base in the web interface
2. The Base ID can be found in the URL: `https://your-nocodb.com/dashboard/#/nc/{BASE_ID}`
3. Copy the Base ID from the URL
4. Paste it into the **NocoDB Base ID** field in the plugin configuration

**Important**: Your API token grants access to your NocoDB bases according to your permissions. Keep it secure and never share it publicly.

## Usage

The plugin provides the following tools that can be used in your Dify applications:

### Retrieve Records

Queries records from a NocoDB table with support for filtering, sorting, and pagination.

**Required parameters:**
- `table_name`: Name of the NocoDB table to query

**Optional parameters:**
- `row_id`: ID of a specific record to retrieve
- `fields`: Comma-separated list of field names to return
- `where`: Filter condition using NocoDB query syntax
- `sort`: Field name to sort by (prefix with '-' for descending order)
- `limit`: Maximum number of records to return (default: 25)
- `offset`: Number of records to skip for pagination (default: 0)

### Create Records

Creates new records in a NocoDB table with support for single or bulk operations.

**Required parameters:**
- `table_name`: Name of the NocoDB table to create records in
- `data`: JSON data containing the field values for the new record(s)

**Optional parameters:**
- `bulk`: Set to true for bulk creation of multiple records (default: false)

**Data format:**
- Single record: `{"column1": "value1", "column2": "value2"}`
- Multiple records: `[{"column1": "value1"}, {"column1": "value2"}]`

### Update Records

Updates existing records in a NocoDB table by ID or in bulk operations.

**Required parameters:**
- `table_name`: Name of the NocoDB table to update records in
- `data`: JSON data containing the field values to update

**Optional parameters:**
- `row_id`: ID of the specific record to update (for single record updates)
- `bulk_ids`: Comma-separated list of record IDs for bulk updates

**Note:** Provide either `row_id` for single updates or `bulk_ids` for bulk updates, not both.

### Delete Records

Removes records from a NocoDB table with support for single or bulk deletion.

**Required parameters:**
- `table_name`: Name of the NocoDB table to delete records from

**Optional parameters:**
- `row_id`: ID of the specific record to delete (for single record deletion)
- `bulk_ids`: Comma-separated list of record IDs for bulk deletion

**Note:** Provide either `row_id` for single deletion or `bulk_ids` for bulk deletion, not both.

### Get Table Schema

Retrieves the complete schema information for a NocoDB table, including column names, data types, and constraints.

**Required parameters:**
- `table_name`: Name of the NocoDB table to get schema information for

This tool is useful for understanding the table structure before creating or updating records.

## Usage Examples

### Basic Record Operations

**Retrieve all records from a table:**
```
Get all customers from the "customers" table
```

**Get a specific record:**
```
Retrieve the customer with ID "rec123" from the "customers" table
```

**Create a new customer:**
```
Create a new customer with name "John Doe", email "john@example.com", and status "active"
```

**Update a customer's information:**
```
Update customer with ID "rec123" to set status as "inactive" and last_login to today's date
```

**Delete a customer:**
```
Delete the customer with ID "rec123" from the customers table
```

### Advanced Operations

**Filter and sort records:**
```
Get customers where status equals "active" and age is greater than 25, sorted by creation date (newest first), limit to 10 records
```

**Bulk operations:**
```
Create multiple customers: [{"name": "Alice", "email": "alice@example.com"}, {"name": "Bob", "email": "bob@example.com"}]
```

**Get table structure:**
```
Show me the schema for the "customers" table so I can understand its structure
```

## Error Handling

The plugin provides detailed error messages for common issues:
- Authentication failures (invalid tokens)
- Table not found errors
- Invalid data format errors
- Network connectivity issues
- Record not found errors

## License

This plugin is licensed under the [MIT License](LICENSE).



