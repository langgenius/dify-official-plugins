# Privacy Policy

## Data Collection

The Neo4j plugin collects and processes the following data:

- **Connection Credentials**: Neo4j URI, username, and password are stored securely and used only to authenticate with your Neo4j database instance.
- **Query Data**: Cypher queries submitted through this plugin are sent directly to your Neo4j database.
- **Query Results**: Results returned from your Neo4j database are processed and displayed within Dify.

## Data Processing

- All data is processed locally within the Dify environment.
- Connection credentials are encrypted and stored securely by Dify's credential management system.
- No query data or results are stored persistently by this plugin beyond the current session.
- Cypher queries are executed directly against your Neo4j instance without modification (except for optional LIMIT clauses for safety).

## Third-party Services

This plugin connects to:

- **Neo4j Database**: Your self-hosted or Neo4j Aura database instance. Please refer to [Neo4j's Privacy Policy](https://neo4j.com/privacy-policy/) for information about how Neo4j handles data.

## Data Retention

- Connection credentials are retained as configured in your Dify workspace settings.
- Query history and results are not retained by this plugin after the session ends.
- Any data stored in your Neo4j database is subject to your own data retention policies.

## User Rights

- You have full control over the credentials stored in Dify.
- You can remove or update credentials at any time through the Dify plugin settings.
- You control what data is queried and modified through the Cypher queries you execute.

## Security Considerations

- This plugin provides both read-only and write operations. Use write operations with caution.
- The read-only tool validates queries to prevent accidental write operations.
- We recommend using a Neo4j user with appropriate permissions for your use case.

## Contact Information

For privacy-related inquiries regarding this plugin, please contact the plugin maintainers through the Dify community channels or GitHub repository.

Last updated: February 2026
