"""
MySQL driver – concrete implementation of DatabaseDriverInterface using SQLAlchemy.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union
from datetime import datetime

from sqlalchemy import create_engine, text
from pydantic import BaseModel

from framework.drivers.base import DatabaseDriverInterface
from framework.drivers.relational_mapper import RelationalMapper

logger = logging.getLogger(__name__)


class MysqlDriver(DatabaseDriverInterface):
    """MySQL driver backed by SQLAlchemy Core."""

    def __init__(self, engine_name: str, connection_params: Dict[str, Any]) -> None:
        super().__init__(engine_name, connection_params)
        self.engine = None
        self.mapper = RelationalMapper()

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
                self.mapper.set_engine_and_connection(self.engine, self._connection)
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
        self.mapper.create_schema(table_defs)

    def create_index(self, table_name: str, column_name: str) -> None:
        self.mapper.create_index(table_name, column_name)

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
        return self.mapper.insert(table_name, entity)

    def insert_many(self, table_name: str, entities: List[Any]) -> Any:
        return self.mapper.insert_many(table_name, entities)

    def update(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        return self.mapper.update(table_name, filter, update_data)

    def update_many(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        return self.mapper.update_many(table_name, filter, update_data)

    def delete(self, table_name: str, filter: Dict) -> Any:
        return self.mapper.delete(table_name, filter)

    def delete_many(self, table_name: str, filter: Dict) -> Any:
        return self.mapper.delete_many(table_name, filter)

    def select(self, table_name: str, filter: Dict, use_explain: bool = False, explain_context: str = None) -> Any:
        return self.mapper.select(table_name, filter, use_explain, explain_context)

    def find_all(self, table_name: str) -> Any:
        return self.mapper.find_all(table_name)

    def count(self, table_name: str, filter: Optional[Dict] = None) -> int:
        return self.mapper.count(table_name, filter)
