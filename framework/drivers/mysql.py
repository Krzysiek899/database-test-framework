"""
MySQL driver – concrete implementation of DatabaseDriverInterface using SQLAlchemy.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime

from sqlalchemy import create_engine, MetaData, Table as SATable, Column, Integer, String, Float, DateTime, Boolean, select, func, text
from pydantic import BaseModel

from framework.drivers.base import DatabaseDriverInterface

logger = logging.getLogger(__name__)


def _map_type(python_type: Any) -> Any:
    """Map python types from Pydantic models to SQLAlchemy types."""
    if python_type == int or python_type == "int":
        return Integer
    if python_type == str or python_type == "str":
        return String(255)
    if python_type == float or python_type == "float":
        return Float
    if python_type == bool or python_type == "bool":
        return Boolean
    if python_type == datetime or python_type == "datetime":
        return DateTime
    return String(255)


class MysqlDriver(DatabaseDriverInterface):
    """MySQL driver backed by SQLAlchemy Core."""

    def __init__(self, engine_name: str, connection_params: Dict[str, Any]) -> None:
        super().__init__(engine_name, connection_params)
        self.engine = None
        self.metadata = MetaData()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        p = self.connection_params
        user = p.get("user", "bench")
        password = p.get("password", "bench")
        host = p.get("host", "127.0.0.1")
        port = p.get("port", 3306)
        dbname = p.get("dbname", "benchdb")

        import time

        url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{dbname}"
        self.engine = create_engine(url, pool_pre_ping=True)

        for attempt in range(10):
            try:
                self._connection = self.engine.connect()
                logger.info("Connected to MySQL on port %s via SQLAlchemy", port)
                return
            except Exception as e:
                logger.debug("MySQL connection attempt %d failed: %s", attempt + 1, e)
                time.sleep(3)

        raise RuntimeError("Could not connect to MySQL after 30 attempts")

    def disconnect(self) -> None:
        if self._connection and not self._connection.closed:
            self._connection.close()
        if self.engine:
            self.engine.dispose()
            logger.info("Disconnected from MySQL")

    def create_schema(self, table_defs: List[Dict[str, Any]]) -> None:
        """Create schema mapping using SQLAlchemy core."""
        for table_def in table_defs:
            table_name = table_def["name"]
            columns = []
            for col in table_def["columns"]:
                columns.append(
                    Column(
                        col["name"],
                        _map_type(col["python_type"]),
                        primary_key=col["primary_key"],
                        nullable=col["nullable"]
                    )
                )

            SATable(table_name, self.metadata, *columns)

        self.metadata.drop_all(self.engine)
        self.metadata.create_all(self.engine)
        logger.info("Recreated MySQL schema with SQLAlchemy Core")

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def get_metrics(self) -> Dict[str, Any]:
        metrics = {}
        try:
            status_res = self._connection.execute(text("SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read_requests';")).fetchone()
            if status_res:
                metrics['cache_read_requests'] = int(status_res[1])
            status_hit_res = self._connection.execute(text("SHOW GLOBAL STATUS LIKE 'Threads_connected';")).fetchone()
            if status_hit_res:
                metrics['threads_connected'] = int(status_hit_res[1])
        except Exception as e:
            logger.warning("Could not fetch metrics for MySQL: %s", e)
            pass
        return metrics

    # ------------------------------------------------------------------
    # Facade Support
    # ------------------------------------------------------------------
    def insert(self, table_name: str, entity: BaseModel) -> Any:
        table = self.metadata.tables[table_name]
        data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
        clean_data = {k: v for k, v in data.items() if not isinstance(v, (list, dict))}
        return self._connection.execute(table.insert().values(**clean_data))

    def insert_many(self, table_name: str, entities: List[Any]) -> Any:
        table = self.metadata.tables[table_name]
        data_list = []
        for entity in entities:
            data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
            clean_data = {k: v for k, v in data.items() if not isinstance(v, (list, dict))}
            data_list.append(clean_data)
        return self._connection.execute(table.insert(), data_list)

    def _build_where_clause(self, table, filter_dict: Dict):
        conditions = []
        for k, v in filter_dict.items():
            if hasattr(table.c, k):
                conditions.append(getattr(table.c, k) == v)
        if not conditions:
            return True
        from sqlalchemy import and_
        return and_(*conditions)

    def update(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = table.update().where(where_clause).values(**update_data)
        return self._connection.execute(stmt)

    def update_many(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = table.update().where(where_clause).values(**update_data)
        return self._connection.execute(stmt)

    def delete(self, table_name: str, filter: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = table.delete().where(where_clause)
        return self._connection.execute(stmt)

    def delete_many(self, table_name: str, filter: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = table.delete().where(where_clause)
        return self._connection.execute(stmt)

    def select(self, table_name: str, filter: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = select(table).where(where_clause)
        return self._connection.execute(stmt).fetchall()

    def find_all(self, table_name: str) -> Any:
        table = self.metadata.tables[table_name]
        return self._connection.execute(select(table)).fetchall()

    def count(self, table_name: str, filter: Optional[Dict] = None) -> int:
        table = self.metadata.tables[table_name]
        stmt = select(func.count()).select_from(table)
        if filter:
            where_clause = self._build_where_clause(table, filter)
            stmt = stmt.where(where_clause)
        return self._connection.execute(stmt).scalar()
