"""
DatabaseDriverInterface – Strategy-pattern base class.
"""

from __future__ import annotations

import abc
from typing import Any, Callable, Dict, List, Optional, Union


class DatabaseDriverInterface(abc.ABC):
    """Abstract base for all database drivers."""

    def __init__(self, engine_name: str, connection_params: Dict[str, Any]) -> None:
        self.engine_name = engine_name
        self.connection_params = connection_params
        self._connection: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def connect(self) -> None:
        """Establish a connection (or pool) to the database."""

    @abc.abstractmethod
    def disconnect(self) -> None:
        """Gracefully close the connection."""

    @abc.abstractmethod
    def create_schema(self, table_defs: List[Dict[str, Any]]) -> None:
        """Create database schema from table definitions."""
        pass

    @abc.abstractmethod
    def create_index(self, table_name: str, column_name: str, **kwargs) -> None:
        """Create an index on the given column. Supports 'unique' kwarg for unique indices."""
        pass

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Return engine-specific diagnostic counters (cache hits, etc.)."""

    # ------------------------------------------------------------------
    # Facade Support
    # ------------------------------------------------------------------
    def get_db_interface(self) -> Any:
        """Returns the facade object over driver."""
        from framework.core.facade import DatabaseFacade
        return DatabaseFacade(self)

    @abc.abstractmethod
    def insert(self, table_name: str, entity: Any) -> Any:
        """Insert a single entity."""
        pass

    @abc.abstractmethod
    def find_all(self, table_name: str) -> Any:
        """Find all entities in a table."""
        pass

    @abc.abstractmethod
    def count(self, table_name: str, filter: Optional[Dict] = None) -> int:
        """Count entities in a table."""
        pass

    @abc.abstractmethod
    def insert_many(self, table_name: str, entities: List[Any]) -> Any:
        """Insert multiple entities."""
        pass

    @abc.abstractmethod
    def update(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        """Update a single entity."""
        pass

    @abc.abstractmethod
    def update_many(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        """Update multiple entities."""
        pass

    @abc.abstractmethod
    def delete(self, table_name: str, filter: Dict) -> Any:
        """Delete a single entity."""
        pass

    @abc.abstractmethod
    def delete_many(self, table_name: str, filter: Dict) -> Any:
        """Delete multiple entities."""
        pass

    @abc.abstractmethod
    def select(self, table_name: str, filter: Dict, use_explain: bool = False, explain_context: str = None) -> Any:
        """Find entities matching filter."""
        pass

    def select_advanced(self, table_name: str, filters: Dict = None, joins: List = None,
                       group_by: List[str] = None, order_by: List[tuple] = None,
                       limit: int = None, offset: int = None, use_explain: bool = False) -> Any:
        """Advanced SELECT with JOIN, GROUP BY, ORDER BY, LIMIT, OFFSET support.
        Optional: drivers can override for their specific implementation."""
        raise NotImplementedError(f"select_advanced not implemented for {self.engine_name}")

    def select_aggregation(self, table_name: str, filters: Dict = None, group_by: List[str] = None,
                          aggregates: Dict[str, tuple] = None, order_by: List[tuple] = None,
                          limit: int = None, use_explain: bool = False) -> Any:
        """SELECT with aggregation (COUNT, AVG, SUM, MIN, MAX).
        Optional: drivers can override for their specific implementation."""
        raise NotImplementedError(f"select_aggregation not implemented for {self.engine_name}")

    # ------------------------------------------------------------------
    # Context-manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "DatabaseDriverInterface":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
