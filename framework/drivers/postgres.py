"""
PostgreSQL driver – concrete implementation of DatabaseDriverInterface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
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


class PostgresDriver(DatabaseDriverInterface):
    """PostgreSQL driver backed by SQLAlchemy Core."""

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
        port = p.get("port", 5432)
        dbname = p.get("dbname", "benchdb")

        # Create SQLAlchemy engine
        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
        self.engine = create_engine(url)
        self._connection = self.engine.connect()
        logger.info("Connected to PostgreSQL on port %s via SQLAlchemy", port)

    def disconnect(self) -> None:
        if self._connection and not self._connection.closed:
            self._connection.close()
        if self.engine:
            self.engine.dispose()
            logger.info("Disconnected from PostgreSQL")

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
        logger.info("Recreated PostgreSQL schema with SQLAlchemy Core")

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def get_metrics(self) -> Dict[str, Any]:
        try:
            result = self._connection.execute(
                text(
                    "SELECT "
                    "  sum(blks_hit)  AS cache_hits, "
                    "  sum(blks_read) AS disk_reads "
                    "FROM pg_stat_database;"
                )
            ).fetchone()
            if result:
                # the result tuple
                return {
                    "cache_hits": result[0],
                    "disk_reads": result[1],
                }
        except Exception as e:
            logger.warning("Could not fetch metrics: %s", e)
        return {}

    # ------------------------------------------------------------------
    # Facade Support
    # ------------------------------------------------------------------
    def insert(self, table_name: str, entity: BaseModel) -> Any:
        table = self.metadata.tables[table_name]
        data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)

        # TODO: Map nested structures to related tables or JSON columns as needed.
        # Remove list or nested dictionaries that shouldn't go directly to SQL columns
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
        # Assuming single update by logic:
        # In SQL, we usually limit or the where clause must be specific (e.g. by id)
        return self._connection.execute(stmt)

    def update_many(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = table.update().where(where_clause).values(**update_data)
        return self._connection.execute(stmt)

    def delete(self, table_name: str, filter: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        # Depending on engine, delete can't easily limit to 1 without specific bindings,
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
