"""
MongoDB driver – concrete implementation of DatabaseDriverInterface.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Union

from pymongo import MongoClient

from framework.drivers.base import DatabaseDriverInterface

logger = logging.getLogger(__name__)


class MongoDriver(DatabaseDriverInterface):
    """MongoDB driver backed by pymongo."""

    def __init__(self, engine_name: str, connection_params: Dict[str, Any]) -> None:
        super().__init__(engine_name, connection_params)
        self._client: Optional[MongoClient] = None
        self._db: Any = None

    def connect(self) -> None:
        p = self.connection_params
        host = p.get("host", "127.0.0.1")
        port = p.get("port", 27017)
        user = p.get("user", "bench")
        password = p.get("password", "bench")
        dbname = p.get("dbname", "benchdb")

        uri = f"mongodb://{user}:{password}@{host}:{port}/{dbname}?authSource=admin"
        self._client = MongoClient(uri)
        self._db = self._client[dbname]
        # Force a round-trip to verify the connection
        self._client.admin.command("ping")
        logger.info("Connected to MongoDB on port %s", port)

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            logger.info("Disconnected from MongoDB")

    @property
    def db(self):
        """Expose the native database handle for callable queries."""
        return self._db

    def execute(
        self,
        query: Union[str, Callable],
        params: Optional[Any] = None,
    ) -> Any:
        if callable(query):
            return query(self._db)
        raise TypeError(
            "MongoDriver.execute() expects a callable, not a raw string. "
            "Pass a function like:  lambda db: db.collection.find({...})"
        )

    def execute_many(
        self,
        query: Union[str, Callable],
        seq_of_params: List[Any],
    ) -> None:
        if callable(query):
            return query(self._db, seq_of_params)
        raise TypeError(
            "MongoDriver.execute_many() expects a callable."
        )

    def get_metrics(self) -> Dict[str, Any]:
        assert self._db is not None
        stats = self._db.command("serverStatus")
        wt = stats.get("wiredTiger", {}).get("cache", {})
        return {
            "cache_bytes_in_use": wt.get("bytes currently in the cache", 0),
            "cache_read_requests": wt.get(
                "pages requested from the cache", 0
            ),
        }

