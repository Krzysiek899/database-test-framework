"""
MongoDB driver – concrete implementation of DatabaseDriverInterface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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

    def create_schema(self, table_defs: List[Dict[str, Any]]) -> None:
        """Drop existing collections explicitly so they start fresh."""
        for table_def in table_defs:
            self._db[table_def["name"]].drop()
        logger.info("Dropped MongoDB existing collections")

    @property
    def db(self):
        """Expose the native database handle for callable queries."""
        return self._db


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

    # ------------------------------------------------------------------
    # Facade Support
    # ------------------------------------------------------------------
    def insert(self, table_name: str, entity: Any) -> Any:
        data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
        # Ensure 'id' is mapped to '_id' for mongo or left as is depending on design.
        # But for compatibility we will push as is.
        self._db[table_name].insert_one(data)

    def insert_many(self, table_name: str, entities: List[Any]) -> Any:
        data_list = []
        for entity in entities:
            data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
            data_list.append(data)
        if data_list:
            self._db[table_name].insert_many(data_list)
        return

    def update(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        return self._db[table_name].update_one(filter, {"$set": update_data})

    def update_many(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        return self._db[table_name].update_many(filter, {"$set": update_data})

    def delete(self, table_name: str, filter: Dict) -> Any:
        return self._db[table_name].delete_one(filter)

    def delete_many(self, table_name: str, filter: Dict) -> Any:
        return self._db[table_name].delete_many(filter)

    def select(self, table_name: str, filter: Dict) -> Any:
        return list(self._db[table_name].find(filter))

    def find_all(self, table_name: str) -> Any:
        return list(self._db[table_name].find())

    def count(self, table_name: str, filter: Optional[Dict] = None) -> int:
        return self._db[table_name].count_documents(filter or {})
