"""
DatabaseDriverInterface – Strategy-pattern base class.

Every concrete driver must implement:
  • connect()    – open a connection / pool
  • disconnect() – close it
  • execute(query) – run a SQL string **or** a callable (NoSQL)
  • get_metrics() – return engine-specific diagnostic info
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

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def execute(
        self,
        query: Union[str, Callable],
        params: Optional[Any] = None,
    ) -> Any:
        """Execute *query*.

        For RDBMS drivers *query* is a SQL string (with optional bind *params*).
        For document-store drivers *query* may be a callable that receives the
        native client/collection and returns a result.
        """

    @abc.abstractmethod
    def execute_many(
        self,
        query: Union[str, Callable],
        seq_of_params: List[Any],
    ) -> None:
        """Batch-execute for bulk inserts / updates."""

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def get_metrics(self) -> Dict[str, Any]:
        """Return engine-specific diagnostic counters (cache hits, etc.)."""

    # ------------------------------------------------------------------
    # Context-manager sugar
    # ------------------------------------------------------------------
    def __enter__(self) -> "DatabaseDriverInterface":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()

