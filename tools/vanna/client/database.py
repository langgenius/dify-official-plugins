import sqlite3
from collections.abc import Callable, Iterator
from contextlib import ExitStack, closing, contextmanager, suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import httpx2
import pandas as pd


@dataclass
class Database:
    dialect: str
    run_sql: Callable[[str], pd.DataFrame]


def _run_sql(connection: Any, sql: str, *, rollback: bool = True) -> pd.DataFrame:
    with closing(connection.cursor()) as cursor:
        try:
            cursor.execute(sql)
            if cursor.description is None:
                raise ValueError("SQL query did not return a result set")
            result = pd.DataFrame.from_records(
                cursor.fetchall(), columns=[column[0] for column in cursor.description]
            )
            return result
        except Exception:
            if rollback:
                # A failed rollback must not hide the query error.
                with suppress(Exception):
                    connection.rollback()
            raise


@contextmanager
def connect_database(parameters: dict[str, Any], http_client: httpx2.Client) -> Iterator[Database]:
    db_type = parameters.get("db_type", "SQLite")
    url = parameters.get("url") or ""
    user = parameters.get("username") or ""
    password = parameters.get("password") or ""
    database = parameters.get("db_name") or ""

    with ExitStack() as stack:
        if db_type in {"SQLite", "DuckDB"} and url.lower().startswith(("https://", "http://")):
            directory = stack.enter_context(TemporaryDirectory(prefix="vanna-database-"))
            path = Path(directory) / "database.db"
            with http_client.stream("GET", url, follow_redirects=True) as response:
                response.raise_for_status()
                with path.open("wb") as output:
                    for chunk in response.iter_bytes():
                        output.write(chunk)
            url = str(path)

        if db_type in {"SQLite", "DuckDB"}:
            is_memory = url == ":memory:" or (db_type == "DuckDB" and not url)
            is_motherduck = db_type == "DuckDB" and url.startswith(("md:", "motherduck:"))
            if not is_memory and not is_motherduck and not Path(url).is_file():
                raise FileNotFoundError(f"Database file does not exist: {url}")

        match db_type:
            case "SQLite":
                connection = sqlite3.connect(url, check_same_thread=False)
                dialect = "SQLite"
            case "Postgres":
                import psycopg2

                connect = partial(
                    psycopg2.connect,
                    host=url,
                    dbname=database,
                    user=user,
                    password=password,
                    port=int(parameters.get("port") or 0),
                )
                # Validate credentials before callers can reset or add training data.
                with closing(connect()):
                    pass

                def run_postgres(sql: str) -> pd.DataFrame:
                    with closing(connect()) as connection:
                        return _run_sql(connection, sql)

                yield Database("PostgreSQL", run_postgres)
                return
            case "DuckDB":
                import duckdb

                connection = stack.enter_context(closing(duckdb.connect(url or ":memory:")))
                yield Database("DuckDB SQL", lambda sql: connection.execute(sql).fetchdf())
                return
            case "SQLServer":
                import pyodbc

                connection = pyodbc.connect(url)
                dialect = "T-SQL / Microsoft SQL Server"
            case "MySQL":
                import pymysql

                connection = pymysql.connect(
                    host=url,
                    database=database,
                    user=user,
                    password=password,
                    port=int(parameters.get("port") or 0),
                )
                dialect = "MySQL"
            case "Oracle":
                import oracledb

                connection = oracledb.connect(user=user, password=password, dsn=url)
                dialect = "Oracle SQL"
            case "Hive":
                from pyhive import hive

                connection = hive.Connection(
                    host=url,
                    database=database,
                    username=user,
                    password=password,
                    port=int(parameters.get("port") or 0),
                    auth="CUSTOM",
                )
                dialect = "HiveQL"
            case "ClickHouse":
                import clickhouse_connect

                connection = stack.enter_context(
                    closing(
                        clickhouse_connect.get_client(
                            host=url,
                            database=database,
                            username=user,
                            password=password,
                            port=int(parameters.get("port") or 0),
                        )
                    )
                )

                def run_clickhouse(sql: str) -> pd.DataFrame:
                    result = connection.query(sql)
                    return pd.DataFrame(result.result_rows, columns=result.column_names)

                yield Database("ClickHouse SQL", run_clickhouse)
                return
            case _:
                raise ValueError(f"Unsupported database type: {db_type}")

        stack.enter_context(closing(connection))

        def run_sql(sql: str) -> pd.DataFrame:
            if db_type == "MySQL":
                connection.ping(reconnect=True)
            if db_type == "Oracle":
                sql = sql.rstrip().removesuffix(";")
            result = _run_sql(connection, sql, rollback=db_type != "Hive")
            if db_type == "SQLServer":
                # The former SQLAlchemy connector closed each transaction without committing.
                connection.rollback()
            return result

        yield Database(dialect, run_sql)
