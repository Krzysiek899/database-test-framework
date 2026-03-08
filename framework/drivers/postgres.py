"""
PostgreSQL driver – concrete implementation of DatabaseDriverInterface.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union

import psycopg2
import psycopg2.extras

from framework.drivers.base import DatabaseDriverInterface

logger = logging.getLogger(__name__)


class PostgresDriver(DatabaseDriverInterface):
    """PostgreSQL driver backed by psycopg2."""

    def connect(self) -> None:
        p = self.connection_params
        self._connection = psycopg2.connect(
            host=p.get("host", "127.0.0.1"),
            port=p.get("port", 5432),
            user=p.get("user", "bench"),
            password=p.get("password", "bench"),
            dbname=p.get("dbname", "benchdb"),
        )
        self._connection.autocommit = True
        logger.info("Connected to PostgreSQL on port %s", p.get("port"))

    def disconnect(self) -> None:
        if self._connection and not self._connection.closed:
            self._connection.close()
            logger.info("Disconnected from PostgreSQL")

    def execute(
        self,
        query: Union[str, Callable],
        params: Optional[Any] = None,
    ) -> Any:
        if callable(query):
            return query(self._connection)
        with self._connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cur:
            cur.execute(query, params)
            if cur.description:
                return cur.fetchall()
            return None

    def execute_many(
        self,
        query: Union[str, Callable],
        seq_of_params: List[Any],
    ) -> None:
        if callable(query):
            return query(self._connection, seq_of_params)
        with self._connection.cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, seq_of_params)

    def get_metrics(self) -> Dict[str, Any]:
        with self._connection.cursor(
            cursor_factory=psycopg2.extras.RealDictCursor,
        ) as cur:
            cur.execute(
                "SELECT "
                "  sum(blks_hit)  AS cache_hits, "
                "  sum(blks_read) AS disk_reads "
                "FROM pg_stat_database;"
            )
            row = cur.fetchone()
            return dict(row) if row else {}

