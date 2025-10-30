# Snowflake SQL

Execute SQL queries on Snowflake data warehouse with secure OAuth 2.0 authentication.

**Author:** langgenius  
**Version:** 0.0.1  
**Type:** Tool Plugin

## Overview

The Snowflake SQL plugin enables seamless integration between Dify AI applications and Snowflake data warehouse. Execute any SQL query securely using OAuth 2.0 authentication, with support for all major SQL operations including SELECT, INSERT, UPDATE, DELETE, and DDL statements.

## Key Features

- 🔐 **OAuth 2.0 Authentication** - Secure, industry-standard authentication
- 🚀 **Full SQL Support** - Execute SELECT, INSERT, UPDATE, DELETE, CREATE, and more
- 📊 **Rich Output Formats** - Results displayed as formatted Markdown tables
- ⚡ **Performance Tracking** - Monitor query execution time
- 🎯 **Flexible Configuration** - Per-query warehouse, database, and schema selection
- 🛡️ **Type-Safe Operations** - Explicit SQL type selection for accurate result handling

## Installation

### Prerequisites

You need a Snowflake account with appropriate permissions to create OAuth integrations. Follow these steps to set up OAuth authentication:

#### 1. Create OAuth Integration in Snowflake

Run the following SQL commands in Snowflake (requires `ACCOUNTADMIN` role):

```sql
USE ROLE ACCOUNTADMIN;

-- Create OAuth integration
CREATE SECURITY INTEGRATION oauth_integration
  TYPE = OAUTH
  ENABLED = TRUE
  OAUTH_CLIENT = CUSTOM
  OAUTH_CLIENT_TYPE = 'CONFIDENTIAL'
  OAUTH_REDIRECT_URI = 'https://your-dify-instance.com/oauth/callback'
  OAUTH_ISSUE_REFRESH_TOKENS = TRUE
  OAUTH_REFRESH_TOKEN_VALIDITY = 7776000  -- 90 days
  BLOCKED_ROLES_LIST = ('ACCOUNTADMIN', 'SECURITYADMIN');
```

#### 2. Retrieve OAuth Credentials

```sql
-- Get Client ID
DESC SECURITY INTEGRATION oauth_integration;

-- Get Client Secret
SELECT SYSTEM$SHOW_OAUTH_CLIENT_SECRETS('OAUTH_INTEGRATION');
```

Copy the `OAUTH_CLIENT_ID` and `OAUTH_CLIENT_SECRET` values - you'll need these for plugin configuration.

#### 3. Grant Necessary Privileges

```sql
-- Create a role for the integration (recommended)
CREATE ROLE IF NOT EXISTS oauth_service_role;

-- Grant warehouse usage
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE oauth_service_role;

-- Grant database and schema access
GRANT USAGE ON DATABASE YOUR_DATABASE TO ROLE oauth_service_role;
GRANT USAGE ON SCHEMA YOUR_DATABASE.PUBLIC TO ROLE oauth_service_role;

-- Grant table permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES 
  IN SCHEMA YOUR_DATABASE.PUBLIC TO ROLE oauth_service_role;

-- Grant integration usage
GRANT USAGE ON INTEGRATION oauth_integration TO ROLE oauth_service_role;

-- Assign role to your user
GRANT ROLE oauth_service_role TO USER your_username;
```

### Install in Dify

1. Navigate to **Tools** > **Manage Tools** in your Dify workspace
2. Search for "Snowflake SQL" in the marketplace
3. Click **Install** to add the plugin
4. Configure OAuth credentials (see Configuration section below)

## Configuration

### OAuth Setup

After installation, configure the following OAuth parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| **Account Name** | Text | Yes | Your Snowflake account identifier (e.g., `xy12345.us-east-1`) |
| **OAuth Client ID** | Secret | Yes | Client ID from `SYSTEM$SHOW_OAUTH_CLIENT_SECRETS` |
| **OAuth Client Secret** | Secret | Yes | Client Secret from `SYSTEM$SHOW_OAUTH_CLIENT_SECRETS` |
| **OAuth Scope** | Text | No | Optional OAuth scope (e.g., `session:role:oauth_service_role`) |

### Authentication Flow

1. Click **Connect with OAuth** in the plugin configuration
2. You'll be redirected to Snowflake's authentication page
3. Log in with your Snowflake credentials
4. Authorize the application to access your Snowflake account
5. You'll be redirected back to Dify with the connection established

The OAuth token is automatically managed and refreshed by the plugin.

## Usage

### Tool Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| **SQL Query** | String | Yes | - | The SQL statement to execute |
| **SQL Type** | Select | Yes | SELECT | Type of SQL operation |
| **Warehouse** | String | No | COMPUTE_WH | Snowflake warehouse name |
| **Database** | String | No | - | Target database |
| **Schema** | String | No | PUBLIC | Target schema |
| **Max Rows** | Number | No | 100 | Maximum rows to return (SELECT only) |

### SQL Types

Select the appropriate SQL type for your query:

- **SELECT** - Retrieve data (returns rows and columns)
- **INSERT** - Add new records (returns affected row count)
- **UPDATE** - Modify existing records (returns affected row count)
- **DELETE** - Remove records (returns affected row count)
- **MERGE** - Upsert operations (returns affected row count)
- **CREATE** - Create database objects (returns execution status)
- **DROP** - Remove database objects (returns execution status)
- **ALTER** - Modify database objects (returns execution status)
- **TRUNCATE** - Clear table data (returns execution status)
- **SHOW** - Display metadata (returns rows and columns)
- **DESCRIBE** - Describe objects (returns rows and columns)
- **OTHER** - Other SQL statements

> **💡 Tip:** Always specify the correct SQL type, especially for queries with WITH clauses, as they can be used with INSERT, UPDATE, or DELETE operations.

## Examples

### Example 1: Query Customer Data

**Input:**
```yaml
sql_query: |
  SELECT 
    customer_id,
    customer_name,
    email,
    total_purchases
  FROM customers
  WHERE total_purchases > 1000
  ORDER BY total_purchases DESC
  LIMIT 20
sql_type: SELECT
max_rows: 20
```

**Output:**
```
✅ SELECT Results (20 rows, 0.234s)

| customer_id | customer_name | email | total_purchases |
| --- | --- | --- | --- |
| C001 | Acme Corporation | contact@acme.com | 15420.50 |
| C002 | TechStart Inc | info@techstart.io | 12350.00 |
```

### Example 2: Insert Order Record

**Input:**
```yaml
sql_query: |
  INSERT INTO orders (order_id, customer_id, amount, status, created_at)
  VALUES ('ORD-2025-001', 'C001', 2499.99, 'pending', CURRENT_TIMESTAMP())
sql_type: INSERT
```

**Output:**
```
✅ INSERT executed successfully
📝 Affected rows: 1
⏱️ Execution time: 0.145s
```

### Example 3: Complex Analytics Query

**Input:**
```yaml
sql_query: |
  WITH monthly_revenue AS (
    SELECT 
      DATE_TRUNC('month', order_date) as month,
      SUM(amount) as revenue
    FROM orders
    WHERE order_date >= DATEADD(month, -12, CURRENT_DATE())
    GROUP BY 1
  )
  SELECT month, revenue
  FROM monthly_revenue
  ORDER BY month DESC
sql_type: SELECT
max_rows: 12
```

## Integration Scenarios

### 1. AI-Powered Data Analysis

Use with Dify Agent to create an intelligent data analyst that can query your database and explain results in natural language.

### 2. Automated Reporting Workflow

Create workflows that generate daily/weekly reports by querying Snowflake and formatting results.

### 3. Customer Support Chatbot

Build chatbots that can look up customer information, order status, and other data in real-time.

## Output Schema

All queries return structured JSON data:

```json
{
  "success": true,
  "sql_type": "SELECT",
  "columns": ["customer_id", "customer_name"],
  "rows": [{"customer_id": "C001", "customer_name": "Acme Corp"}],
  "row_count": 1,
  "executed_sql": "SELECT ...",
  "execution_time": 0.234
}
```

## Best Practices

### Security

- ✅ Use OAuth with minimum required privileges
- ✅ Create dedicated service roles for integration
- ✅ Block privileged roles in OAuth integration
- ❌ Don't grant unnecessary permissions

### Performance

- ✅ Use `LIMIT` clauses to reduce data transfer
- ✅ Specify appropriate `max_rows` parameter
- ❌ Avoid `SELECT *` on large tables

### Query Design

- ✅ Always specify SQL type correctly
- ✅ Test queries in Snowflake before production use
- ❌ Don't use dynamic SQL from untrusted input

## Troubleshooting

### Authentication Errors

**Error:** "OAuth authentication required"

**Solution:** Reconnect OAuth in plugin settings.

### Query Errors

**Error:** "SQL compilation error: Object does not exist"

**Solution:** Verify database, schema, and table names. Check permissions.

### Permission Errors

**Error:** "Insufficient privileges to operate on table"

**Solution:** Grant necessary permissions to your OAuth role.

## Support

- 📖 [Snowflake Documentation](https://docs.snowflake.com/)
- 💬 [Dify Community](https://github.com/langgenius/dify/discussions)
- 🐛 [Report Issues](https://github.com/langgenius/dify/issues)

## Development Notes

### Plugin Structure

```
snowflake_sql/
├── manifest.yaml          # Plugin metadata
├── requirements.txt       # Python dependencies
├── main.py               # Entry point
├── README.md             # Documentation
├── provider/
│   ├── snowflake_sql.py  # OAuth provider implementation
│   └── snowflake_sql.yaml # Provider configuration
└── tools/
    ├── snowflake_sql.py   # Tool implementation
    └── snowflake_sql.yaml # Tool definition
```

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the plugin locally
python main.py
```

### Key Implementation Details

**Provider (`provider/snowflake_sql.py`):**
- Implements OAuth 2.0 authorization code flow
- Handles token exchange and refresh
- Validates credentials by testing Snowflake connection

**Tool (`tools/snowflake_sql.py`):**
- Executes SQL queries using OAuth token
- Supports multiple SQL types (SELECT, INSERT, UPDATE, etc.)
- Formats results as Markdown tables and JSON
- Handles errors gracefully with detailed messages

## License

Apache License 2.0

This plugin uses the following open-source libraries:
- [snowflake-connector-python](https://github.com/snowflakedb/snowflake-connector-python) - Apache-2.0 License
- [dify-plugin](https://github.com/langgenius/dify-plugin-sdks) - Apache-2.0 License

