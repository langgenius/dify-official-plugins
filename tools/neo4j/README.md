## Neo4j

**Author:** langgenius
**Version:** 0.0.1
**Type:** tool

### Description

The Neo4j plugin enables Dify AI agents to interact with Neo4j graph databases. It provides tools for exploring database schemas, executing read and write Cypher queries, and discovering Graph Data Science (GDS) procedures for advanced analytics.

### Features

- **Get Schema**: Retrieve database structure including node labels, relationship types, property keys, indexes, and constraints
- **Read Cypher Query**: Execute read-only Cypher queries safely with automatic write operation detection
- **Write Cypher Query**: Execute write operations (CREATE, MERGE, SET, DELETE) with detailed statistics
- **List GDS Procedures**: Discover available Graph Data Science algorithms for graph analytics

### Installation

1. Install the plugin from the Dify Marketplace
2. Configure your Neo4j connection credentials:
   - **URI**: Your Neo4j connection string (e.g., `bolt://localhost:7687` or `neo4j+s://xxxx.databases.neo4j.io`)
   - **Username**: Your Neo4j username (default is usually `neo4j`)
   - **Password**: Your Neo4j password

### Configuration

The plugin supports various Neo4j deployment types:

| Deployment Type | URI Format |
|----------------|------------|
| Local/Docker | `bolt://localhost:7687` |
| Neo4j Aura | `neo4j+s://xxxx.databases.neo4j.io` |
| Self-hosted with TLS | `bolt+s://your-server:7687` |

### Usage Examples

#### Get Database Schema
Use the "Get Schema" tool to understand your database structure before writing queries.

#### Read Data
```cypher
MATCH (p:Person)-[:KNOWS]->(friend)
WHERE p.name = 'Alice'
RETURN friend.name, friend.age
```

#### Create Data
```cypher
CREATE (p:Person {name: 'Bob', age: 30})
RETURN p
```

#### Create Relationships
```cypher
MATCH (a:Person {name: 'Alice'}), (b:Person {name: 'Bob'})
CREATE (a)-[:KNOWS {since: 2024}]->(b)
```

#### Use GDS Algorithms
First, list available GDS procedures with a filter (e.g., "pagerank"), then execute the algorithm using write queries.

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | Check that Neo4j is running and the URI is correct |
| Authentication failed | Verify username and password |
| GDS not found | Install the Graph Data Science library on your Neo4j instance |
| Write operations blocked | Use the "Write Cypher Query" tool instead of "Read Cypher Query" |

### Security Best Practices

1. Use a dedicated Neo4j user with minimal required permissions
2. For read-only use cases, configure a user without write permissions
3. Consider using the read-only tool for exploratory queries
4. Review generated queries before executing write operations

### Resources

- [Neo4j Documentation](https://neo4j.com/docs/)
- [Cypher Query Language](https://neo4j.com/docs/cypher-manual/)
- [Graph Data Science Library](https://neo4j.com/docs/graph-data-science/)
- [Neo4j Aura](https://neo4j.com/cloud/aura/)

### License

This plugin is released under the same license as the Dify platform.
