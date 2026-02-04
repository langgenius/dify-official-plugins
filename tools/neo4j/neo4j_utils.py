from typing import Any
from neo4j import GraphDatabase
from neo4j.graph import Node, Relationship, Path
from neo4j.time import DateTime, Date, Time, Duration
from neo4j.spatial import Point


class Neo4jUtils:
    """Utility class for Neo4j database operations."""

    @staticmethod
    def convert_neo4j_types(value: Any) -> Any:
        """
        Convert Neo4j-specific types to JSON-serializable Python types.

        Args:
            value: Any value that might contain Neo4j-specific types

        Returns:
            JSON-serializable Python value
        """
        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, DateTime):
            return value.iso_format()
        elif isinstance(value, Date):
            return value.iso_format()
        elif isinstance(value, Time):
            return value.iso_format()
        elif isinstance(value, Duration):
            return {
                "months": value.months,
                "days": value.days,
                "seconds": value.seconds,
                "nanoseconds": value.nanoseconds
            }
        elif isinstance(value, Point):
            return {
                "srid": value.srid,
                "x": value.x,
                "y": value.y,
                "z": getattr(value, 'z', None)
            }
        elif isinstance(value, Node):
            return {
                "id": value.element_id,
                "labels": list(value.labels),
                "properties": Neo4jUtils.convert_neo4j_types(dict(value))
            }
        elif isinstance(value, Relationship):
            return {
                "id": value.element_id,
                "type": value.type,
                "start_node_id": value.start_node.element_id if value.start_node else None,
                "end_node_id": value.end_node.element_id if value.end_node else None,
                "properties": Neo4jUtils.convert_neo4j_types(dict(value))
            }
        elif isinstance(value, Path):
            return {
                "nodes": [Neo4jUtils.convert_neo4j_types(node) for node in value.nodes],
                "relationships": [Neo4jUtils.convert_neo4j_types(rel) for rel in value.relationships]
            }
        elif isinstance(value, dict):
            return {k: Neo4jUtils.convert_neo4j_types(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [Neo4jUtils.convert_neo4j_types(item) for item in value]
        else:
            # Fallback: convert to string
            return str(value)

    @staticmethod
    def get_driver(uri: str, username: str, password: str):
        """
        Create a Neo4j driver instance.

        Args:
            uri: Neo4j connection URI (e.g., bolt://localhost:7687)
            username: Neo4j username
            password: Neo4j password

        Returns:
            Neo4j driver instance
        """
        return GraphDatabase.driver(uri, auth=(username, password))

    @staticmethod
    def verify_connectivity(uri: str, username: str, password: str) -> bool:
        """
        Verify connection to Neo4j database.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password

        Returns:
            True if connection is successful

        Raises:
            Exception if connection fails
        """
        driver = Neo4jUtils.get_driver(uri, username, password)
        try:
            driver.verify_connectivity()
            return True
        finally:
            driver.close()

    @staticmethod
    def get_schema(uri: str, username: str, password: str) -> dict[str, Any]:
        """
        Get the database schema including labels, relationship types, and property keys.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password

        Returns:
            Dictionary containing schema information
        """
        driver = Neo4jUtils.get_driver(uri, username, password)
        try:
            with driver.session() as session:
                # Get node labels
                labels_result = session.run("CALL db.labels()")
                labels = [record["label"] for record in labels_result]

                # Get relationship types
                rel_types_result = session.run("CALL db.relationshipTypes()")
                relationship_types = [record["relationshipType"] for record in rel_types_result]

                # Get property keys
                property_keys_result = session.run("CALL db.propertyKeys()")
                property_keys = [record["propertyKey"] for record in property_keys_result]

                # Get constraints
                constraints = []
                try:
                    constraints_result = session.run("SHOW CONSTRAINTS")
                    constraints = [dict(record) for record in constraints_result]
                except Exception:
                    # Older Neo4j versions may not support SHOW CONSTRAINTS
                    pass

                # Get indexes
                indexes = []
                try:
                    indexes_result = session.run("SHOW INDEXES")
                    indexes = [dict(record) for record in indexes_result]
                except Exception:
                    # Older Neo4j versions may not support SHOW INDEXES
                    pass

                return Neo4jUtils.convert_neo4j_types({
                    "labels": labels,
                    "relationship_types": relationship_types,
                    "property_keys": property_keys,
                    "constraints": constraints,
                    "indexes": indexes
                })
        finally:
            driver.close()

    @staticmethod
    def execute_read_cypher(uri: str, username: str, password: str, query: str,
                            parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """
        Execute a read-only Cypher query.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            List of result records as dictionaries
        """
        driver = Neo4jUtils.get_driver(uri, username, password)
        try:
            with driver.session() as session:
                result = session.execute_read(
                    lambda tx: list(tx.run(query, parameters or {}).data())
                )
                return Neo4jUtils.convert_neo4j_types(result)
        finally:
            driver.close()

    @staticmethod
    def execute_write_cypher(uri: str, username: str, password: str, query: str,
                             parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Execute a write Cypher query.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password
            query: Cypher query string
            parameters: Optional query parameters

        Returns:
            Dictionary containing query results and statistics
        """
        driver = Neo4jUtils.get_driver(uri, username, password)
        try:
            with driver.session() as session:
                def write_transaction(tx):
                    result = tx.run(query, parameters or {})
                    data = list(result.data())
                    summary = result.consume()
                    counters = summary.counters
                    return {
                        "data": Neo4jUtils.convert_neo4j_types(data),
                        "statistics": {
                            "nodes_created": counters.nodes_created,
                            "nodes_deleted": counters.nodes_deleted,
                            "relationships_created": counters.relationships_created,
                            "relationships_deleted": counters.relationships_deleted,
                            "properties_set": counters.properties_set,
                            "labels_added": counters.labels_added,
                            "labels_removed": counters.labels_removed,
                            "indexes_added": counters.indexes_added,
                            "indexes_removed": counters.indexes_removed,
                            "constraints_added": counters.constraints_added,
                            "constraints_removed": counters.constraints_removed
                        }
                    }
                result = session.execute_write(write_transaction)
                return result
        finally:
            driver.close()

    @staticmethod
    def list_gds_procedures(uri: str, username: str, password: str) -> list[dict[str, Any]]:
        """
        List available Graph Data Science (GDS) procedures.

        Args:
            uri: Neo4j connection URI
            username: Neo4j username
            password: Neo4j password

        Returns:
            List of GDS procedures with their descriptions
        """
        driver = Neo4jUtils.get_driver(uri, username, password)
        try:
            with driver.session() as session:
                # Check if GDS is available
                try:
                    result = session.run("""
                        CALL dbms.procedures()
                        YIELD name, description, signature, mode
                        WHERE name STARTS WITH 'gds.'
                        RETURN name, description, signature, mode
                        ORDER BY name
                    """)
                    procedures = [dict(record) for record in result]
                    return Neo4jUtils.convert_neo4j_types(procedures)
                except Exception as e:
                    if "gds" in str(e).lower() or "procedure" in str(e).lower():
                        return []
                    raise
        finally:
            driver.close()

    @staticmethod
    def is_read_only_query(query: str) -> bool:
        """
        Check if a Cypher query is read-only.

        Args:
            query: Cypher query string

        Returns:
            True if the query appears to be read-only
        """
        query_upper = query.upper().strip()

        # List of write operations
        write_keywords = [
            'CREATE', 'MERGE', 'SET', 'DELETE', 'REMOVE', 'DETACH',
            'DROP', 'LOAD CSV', 'FOREACH', 'CALL {'  # subquery writes
        ]

        # List of admin operations
        admin_keywords = [
            'CREATE DATABASE', 'DROP DATABASE', 'CREATE USER', 'DROP USER',
            'ALTER USER', 'CREATE ROLE', 'DROP ROLE', 'GRANT', 'REVOKE',
            'CREATE INDEX', 'DROP INDEX', 'CREATE CONSTRAINT', 'DROP CONSTRAINT'
        ]

        for keyword in write_keywords + admin_keywords:
            if keyword in query_upper:
                return False

        return True
