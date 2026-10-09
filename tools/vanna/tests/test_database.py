import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import duckdb
import httpx2

from client.database import connect_database


class DatabaseTest(unittest.TestCase):
    def test_local_databases_query_schema_and_preserve_transaction_behavior(self):
        with tempfile.TemporaryDirectory() as directory, httpx2.Client() as client:
            for kind in ("SQLite", "DuckDB"):
                with self.subTest(database=kind):
                    parameters = {"db_type": kind, "url": str(Path(directory) / kind)}
                    connector = sqlite3.connect if kind == "SQLite" else duckdb.connect
                    connection = connector(parameters["url"])
                    try:
                        connection.execute("CREATE TABLE customers (name VARCHAR)")
                        connection.execute("INSERT INTO customers VALUES ('Ada')")
                        connection.commit()
                    finally:
                        connection.close()
                    with connect_database(parameters, client) as database:
                        result = database.run_sql("SELECT name FROM customers")
                        self.assertEqual(result.to_dict("records"), [{"name": "Ada"}])
                        empty = database.run_sql("SELECT name FROM customers WHERE 1 = 0")
                        self.assertEqual(empty.columns.tolist(), ["name"])
                        self.assertTrue(empty.empty)
                        schema_sql = (
                            "SELECT sql FROM sqlite_master WHERE name = 'customers'"
                            if kind == "SQLite"
                            else "SELECT column_name FROM information_schema.columns "
                            "WHERE table_name = 'customers'"
                        )
                        self.assertFalse(database.run_sql(schema_sql).empty)
                        database.run_sql("INSERT INTO customers VALUES ('Grace') RETURNING name")
                    with connect_database(parameters, client) as database:
                        self.assertEqual(
                            database.run_sql("SELECT name FROM customers")["name"].tolist(),
                            ["Ada"] if kind == "SQLite" else ["Ada", "Grace"],
                        )

    def test_missing_local_databases_are_not_created(self):
        with tempfile.TemporaryDirectory() as directory, httpx2.Client() as client:
            for kind in ("SQLite", "DuckDB"):
                with self.subTest(database=kind):
                    path = Path(directory) / kind
                    with (
                        self.assertRaises(FileNotFoundError),
                        connect_database({"db_type": kind, "url": str(path)}, client),
                    ):
                        self.fail("A missing database must not be created implicitly")
                    self.assertFalse(path.exists())

    def test_memory_and_motherduck_connection_urls(self):
        with httpx2.Client() as client:
            for kind in ("SQLite", "DuckDB"):
                with connect_database({"db_type": kind, "url": ":memory:"}, client) as database:
                    self.assertEqual(database.run_sql("SELECT 1 AS value")["value"].tolist(), [1])
            for url in ("md:analytics", "motherduck:analytics"):
                with self.subTest(url=url):
                    connect = Mock()
                    with (
                        patch.dict(sys.modules, {"duckdb": SimpleNamespace(connect=connect)}),
                        connect_database({"db_type": "DuckDB", "url": url}, client),
                    ):
                        pass
                    connect.assert_called_once_with(url)
                    connect.return_value.close.assert_called_once()

    def test_downloaded_sqlite_uses_unique_temporary_files_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.sqlite"
            with sqlite3.connect(source) as connection:
                connection.execute("CREATE TABLE customers (name TEXT)")
                connection.execute("INSERT INTO customers VALUES ('Ada')")
            payload = source.read_bytes()
            source.unlink()

            def download(request):
                if request.url.path == "/customers.sqlite":
                    return httpx2.Response(302, headers={"Location": "/download.sqlite"})
                return httpx2.Response(200, content=payload)

            transport = httpx2.MockTransport(download)
            real_connect = sqlite3.connect
            paths = []
            parameters = {
                "db_type": "SQLite",
                "url": "https://example.com/customers.sqlite",
            }
            with (
                httpx2.Client(transport=transport) as client,
                patch("sqlite3.connect", side_effect=real_connect) as connect,
                patch("tempfile.tempdir", directory),
            ):
                for _ in range(2):
                    with connect_database(parameters, client) as database:
                        path = Path(connect.call_args.args[0])
                        paths.append(path)
                        self.assertTrue(path.exists())
                        self.assertEqual(
                            database.run_sql("SELECT name FROM customers")["name"].tolist(),
                            ["Ada"],
                        )
                    self.assertFalse(path.exists())
                with (
                    self.assertRaises(sqlite3.OperationalError),
                    connect_database(parameters, client) as database,
                ):
                    database.run_sql("SELECT * FROM missing_table")
                self.assertFalse(Path(connect.call_args.args[0]).exists())
            self.assertNotEqual(paths[0], paths[1])
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_failed_download_leaves_no_database_file(self):
        transport = httpx2.MockTransport(lambda request: httpx2.Response(503))
        with (
            tempfile.TemporaryDirectory() as directory,
            httpx2.Client(transport=transport) as client,
            patch("tempfile.tempdir", directory),
            patch("sqlite3.connect") as connect,
        ):
            with (
                self.assertRaises(httpx2.HTTPStatusError),
                connect_database(
                    {"db_type": "SQLite", "url": "https://example.com/unavailable"},
                    client,
                ),
            ):
                self.fail("A failed download must not open a database")
            connect.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_remote_database_parameters_results_and_cleanup(self):
        parameters = {
            "url": "server",
            "db_name": "analytics",
            "username": "reader",
            "password": "secret",
            "port": 1234,
        }
        cases = [
            (
                "Postgres",
                "psycopg2",
                "connect",
                (),
                {
                    "host": "server",
                    "dbname": "analytics",
                    "user": "reader",
                    "password": "secret",
                    "port": 1234,
                },
            ),
            (
                "MySQL",
                "pymysql",
                "connect",
                (),
                {
                    "host": "server",
                    "database": "analytics",
                    "user": "reader",
                    "password": "secret",
                    "port": 1234,
                },
            ),
            ("SQLServer", "pyodbc", "connect", ("server",), {}),
            (
                "Oracle",
                "oracledb",
                "connect",
                (),
                {
                    "user": "reader",
                    "password": "secret",
                    "dsn": "server",
                },
            ),
            (
                "Hive",
                "pyhive.hive",
                "Connection",
                (),
                {
                    "host": "server",
                    "database": "analytics",
                    "username": "reader",
                    "password": "secret",
                    "port": 1234,
                    "auth": "CUSTOM",
                },
            ),
        ]
        with httpx2.Client() as client:
            for kind, module_name, factory_name, args, kwargs in cases:
                for fails in (False, True):
                    with self.subTest(database=kind, query_fails=fails):
                        cursor = Mock(description=[("name",)])
                        cursor.fetchall.return_value = [("Ada",)]
                        connection = Mock()
                        connection.cursor.return_value = cursor
                        factory = Mock(return_value=connection)
                        if kind == "Postgres":
                            validation_connection = Mock()
                            factory.side_effect = [validation_connection, connection]
                        module = SimpleNamespace(**{factory_name: factory})
                        modules = {module_name: module}
                        if kind == "Hive":
                            modules["pyhive"] = SimpleNamespace(hive=module)
                        if fails:
                            cursor.execute.side_effect = RuntimeError("query failed")
                        with patch.dict(sys.modules, modules):
                            if fails:
                                with (
                                    self.assertRaisesRegex(RuntimeError, "query failed"),
                                    connect_database(
                                        {**parameters, "db_type": kind}, client
                                    ) as database,
                                ):
                                    database.run_sql("SELECT name FROM customers;")
                            else:
                                with connect_database(
                                    {**parameters, "db_type": kind}, client
                                ) as database:
                                    result = database.run_sql("SELECT name FROM customers;")
                                    self.assertEqual(result.to_dict("records"), [{"name": "Ada"}])
                        self.assertEqual(factory.call_args.args, args)
                        for key, value in kwargs.items():
                            self.assertEqual(factory.call_args.kwargs[key], value)
                        cursor.execute.assert_called_once_with(
                            "SELECT name FROM customers"
                            if kind == "Oracle"
                            else "SELECT name FROM customers;"
                        )
                        cursor.close.assert_called_once()
                        connection.close.assert_called_once()
                        if kind == "Postgres":
                            validation_connection.close.assert_called_once()
                            validation_connection.cursor.assert_not_called()
                            validation_connection.commit.assert_not_called()
                        connection.commit.assert_not_called()

    def test_postgres_connection_failure_blocks_entering_database_context(self):
        connect = Mock(side_effect=RuntimeError("invalid database credentials"))
        with (
            httpx2.Client() as client,
            patch.dict(sys.modules, {"psycopg2": SimpleNamespace(connect=connect)}),
            self.assertRaisesRegex(RuntimeError, "invalid database credentials"),
            connect_database({"db_type": "Postgres", "url": "server"}, client),
        ):
            self.fail("Database credentials must be verified before training can run")
        connect.assert_called_once()

    def test_sqlserver_returning_statement_does_not_commit(self):
        with tempfile.TemporaryDirectory() as directory, httpx2.Client() as client:
            path = str(Path(directory) / "transactions.sqlite")
            connection = sqlite3.connect(path)
            try:
                connection.execute("CREATE TABLE customers (name TEXT)")
                connection.execute("INSERT INTO customers VALUES ('Ada')")
                connection.commit()
            finally:
                connection.close()
            # SQLite supplies a real DB-API transaction behind the mocked ODBC driver.
            with patch.dict(sys.modules, {"pyodbc": SimpleNamespace(connect=sqlite3.connect)}):
                with connect_database({"db_type": "SQLServer", "url": path}, client) as database:
                    result = database.run_sql(
                        "INSERT INTO customers VALUES ('Grace') RETURNING name"
                    )
                    self.assertEqual(result["name"].tolist(), ["Grace"])
                    self.assertEqual(
                        database.run_sql("SELECT name FROM customers")["name"].tolist(),
                        ["Ada"],
                    )
                with connect_database({"db_type": "SQLServer", "url": path}, client) as database:
                    self.assertEqual(
                        database.run_sql("SELECT name FROM customers")["name"].tolist(), ["Ada"]
                    )

    def test_sqlserver_statement_without_results_rolls_back(self):
        cursor = Mock(description=None)
        connection = Mock()
        connection.cursor.return_value = cursor
        with (
            httpx2.Client() as client,
            patch.dict(
                sys.modules,
                {"pyodbc": SimpleNamespace(connect=Mock(return_value=connection))},
            ),
            connect_database({"db_type": "SQLServer", "url": "server"}, client) as database,
            self.assertRaisesRegex(ValueError, "result set"),
        ):
            database.run_sql("DELETE FROM customers")
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once()
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    def test_clickhouse_parameters_results_and_cleanup(self):
        with httpx2.Client() as client:
            for fails in (False, True):
                with self.subTest(query_fails=fails):
                    connection = Mock()
                    connection.query.return_value = SimpleNamespace(
                        result_rows=[("Ada",)], column_names=["name"]
                    )
                    factory = Mock(return_value=connection)
                    if fails:
                        connection.query.side_effect = RuntimeError("query failed")
                    with patch.dict(
                        sys.modules,
                        {
                            "clickhouse_connect": SimpleNamespace(get_client=factory),
                        },
                    ):
                        parameters = {
                            "db_type": "ClickHouse",
                            "url": "server",
                            "port": 8123,
                            "username": "reader",
                            "password": "secret",
                            "db_name": "analytics",
                        }
                        if fails:
                            with (
                                self.assertRaisesRegex(RuntimeError, "query failed"),
                                connect_database(parameters, client) as database,
                            ):
                                database.run_sql("SELECT name FROM customers")
                        else:
                            with connect_database(parameters, client) as database:
                                result = database.run_sql("SELECT name FROM customers")
                                self.assertEqual(result.to_dict("records"), [{"name": "Ada"}])
                    factory.assert_called_once_with(
                        host="server",
                        port=8123,
                        username="reader",
                        password="secret",
                        database="analytics",
                    )
                    connection.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
