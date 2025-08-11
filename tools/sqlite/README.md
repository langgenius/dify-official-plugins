# SQLite Plugin

**Author:** langgenius  
**Version:** 0.0.1  
**Type:** Dify Plugin Tool

## Description
A universal SQLite database tool for AI agents to query, manage, and analyze databases. Supports both SQL and JSON-based actions for easy, safe, and flexible data operations. Works with local files, cloud databases, and in-memory databases.

## Features
- **Universal Connection:** Connect to any SQLite database via file path
- **Dual Interface:** Support for both SQL statements and JSON-based operations
- **Comprehensive Operations:**
  - Create and drop tables
  - Insert single or multiple rows
  - Update rows with conditions
  - Delete rows or entire tables
  - Advanced SELECT queries (aggregates, window functions, recursive CTEs)
- **Multi-language Support:** English, Chinese (Simplified/Traditional), Japanese, Portuguese
- **Security:** Parameterized queries to prevent SQL injection
- **Error Handling:** Friendly error messages and detailed result reporting
- **Flexible Output:** Results available in both text and JSON formats

## Configuration
- **Database File Path:** The absolute or relative path to your SQLite `.db` file
- **Access Requirements:** The database file must be accessible from the plugin environment
- **Permissions:** The plugin requires read/write access to the database file

## Available Tools

### 1. Create Table
Creates a new table in the SQLite database using SQL CREATE TABLE statements.

**Parameters:**
- `create_table_sql` (required): SQL CREATE TABLE statement

**Example:**
```sql
CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE)
```

### 2. Select Rows
Executes SQL SELECT statements to query data from tables.

**Parameters:**
- `select_sql` (required): SQL SELECT statement

**Examples:**
```sql
SELECT * FROM users WHERE name = 'Alice'
```

```sql
SELECT name, COUNT(*) as count FROM users GROUP BY name
```

### 3. Insert Rows (SQL)
Inserts data using SQL INSERT statements.

**Parameters:**
- `insert_sql` (required): SQL INSERT statement

**Examples:**
```sql
INSERT INTO users (id, name, email) VALUES (1, 'Alice', 'alice@example.com')
```

```sql
INSERT INTO users (name, email) VALUES ('Bob', 'bob@example.com'), ('Charlie', 'charlie@example.com')
```

### 4. Insert Rows (JSON)
Inserts data using JSON format for easier programmatic access.

**Parameters:**
- `table` (required): Name of the table to insert into
- `data` (required): JSON string of data to insert (single object or array of objects)

**Examples:**

Single row:
```json
{
  "table": "users",
  "data": "{\"id\": 2, \"name\": \"Bob\", \"email\": \"bob@example.com\"}"
}
```

Multiple rows:
```json
{
  "table": "users",
  "data": "[{\"id\": 3, \"name\": \"Charlie\", \"email\": \"charlie@example.com\"}, {\"id\": 4, \"name\": \"Dana\", \"email\": \"dana@example.com\"}]"
}
```

### 5. Update Rows (SQL)
Updates data using SQL UPDATE statements.

**Parameters:**
- `update_sql` (required): SQL UPDATE statement

**Example:**
```sql
UPDATE users SET name = 'Alice Smith', email = 'alice.smith@example.com' WHERE id = 1
```

### 6. Update Rows (JSON)
Updates data using JSON format with separate data and condition parameters.

**Parameters:**
- `table` (required): Name of the table to update
- `data` (required): JSON string with columns and new values
- `where` (required): JSON string with conditions for selecting rows to update

**Example:**
```json
{
  "table": "users",
  "data": "{\"name\": \"Alice Smith\", \"email\": \"alice.smith@example.com\"}",
  "where": "{\"id\": 1}"
}
```

### 7. Delete Rows or Tables
Deletes rows or entire tables using SQL DELETE or DROP statements.

**Parameters:**
- `delete_sql` (required): SQL DELETE or DROP statement

**Examples:**

Delete specific rows:
```sql
DELETE FROM users WHERE id = 1
```

Delete all rows:
```sql
DELETE FROM users
```

Drop entire table:
```sql
DROP TABLE users
```

## Advanced Usage Examples

### Complex Queries
```sql
SELECT u.name, COUNT(o.id) as order_count 
FROM users u 
LEFT JOIN orders o ON u.id = o.user_id 
GROUP BY u.id, u.name 
HAVING order_count > 0 
ORDER BY order_count DESC
```

### Window Functions
```sql
SELECT name, salary, 
       ROW_NUMBER() OVER (PARTITION BY department ORDER BY salary DESC) as rank 
FROM employees
```

### Recursive CTEs
```sql
WITH RECURSIVE categories AS (
    SELECT id, name, parent_id, 0 as level 
    FROM category 
    WHERE parent_id IS NULL 
    UNION ALL 
    SELECT c.id, c.name, c.parent_id, cat.level + 1 
    FROM category c 
    JOIN categories cat ON c.parent_id = cat.id
) 
SELECT * FROM categories
```

## Error Handling
The plugin provides detailed error messages for common issues:
- Invalid SQL syntax
- Table/column not found
- Constraint violations
- File access permissions
- Database corruption

## Security Considerations
- All SQL operations use parameterized queries to prevent SQL injection
- Input validation is performed on all parameters
- Database file path is validated for security
- Error messages are sanitized to prevent information leakage

## Performance Tips
- Use appropriate indexes for frequently queried columns
- Batch insert operations when inserting multiple rows
- Use transactions for multiple related operations
- Consider using JSON operations for simpler data structures
- Use specific column names in SELECT statements rather than `SELECT *`

## Support
For issues, questions, or contributions, please refer to the Dify plugin documentation or contact the development team.
