import datetime
import logging
from typing import Optional
from uuid import UUID

import pandas as pd
from pandas import Timestamp
from sqlalchemy import create_engine


class DbUtil:

    def __init__(self, db_type: str,
                 username: str, password: str,
                 host: str, port: Optional[str] = None,
                 database: Optional[str] = None,
                 properties: Optional[str] = None) -> None:
        self.db_type = db_type
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.database = database
        self.properties = properties
        self.engine = create_engine(self.get_url(), pool_size=100, pool_recycle=36)

    def get_driver_name(self):
        driver_name = self.db_type
        if self.db_type == 'mysql':
            driver_name = 'mysql+pymysql'
        elif self.db_type == 'oracle':
            driver_name = 'oracle+oracledb'
        elif self.db_type == 'postgresql':
            driver_name = 'postgresql+psycopg2'
        return driver_name

    def get_url(self):
        '''
        Get url
        '''
        url = f"{self.get_driver_name()}://{self.username}:{self.password}@{self.host}"
        if self.is_not_empty(self.port):
            url = f"{url}:{str(self.port)}"
        url = f"{url}/"
        if self.is_not_empty(self.database):
            url = f"{url}{self.database}"
        if self.is_not_empty(self.properties):
            url = f"{url}?{self.properties}"
        logging.info(f"url={url}")
        return url

    def run_query(self, query_sql: str) -> list[dict]:
        '''
        Run SQL Query
        '''
        query_sql = query_sql.replace('%', '%%')
        df = pd.read_sql_query(sql=query_sql, con=self.engine, parse_dates="%Y-%m-%d %H:%M:%S")
        df = df.fillna('')
        records = []
        if len(df) > 0:
            records = df.to_dict(orient="records")
        for record in records:
            for key in record:
                # print(type(record[key]))
                if type(record[key]) is Timestamp:
                    record[key] = record[key].strftime('%Y-%m-%d %H:%M:%S')
                if type(record[key]) is datetime.date:
                    record[key] = record[key].strftime('%Y-%m-%d')
                if type(record[key]) is UUID:
                    record[key] = str(record[key])
        return records

    def test_sql(self):
        if self.db_type in {'mysql', 'postgresql'}:
            return "SELECT 1"
        elif self.db_type == 'oracle':
            return "SELECT 1 FROM DUAL"

    @staticmethod
    def is_not_empty(s: str):
        return s is not None and s.strip() != ""
