"""
DriverFactory – Factory Pattern for instantiating the correct driver.
"""

from __future__ import annotations

from typing import Any, Dict

from framework.drivers.base import DatabaseDriverInterface
from framework.drivers.postgres import PostgresDriver
from framework.drivers.mongo import MongoDriver

_REGISTRY: Dict[str, type] = {
    "postgres": PostgresDriver,
    "mongodb": MongoDriver,
}


def create_driver(
    engine_name: str,
    engine_type: str,
    connection_params: Dict[str, Any],
) -> DatabaseDriverInterface:
    """Create and return the appropriate driver instance.

    Parameters
    ----------
    engine_name:
        Human-readable label (e.g. "postgres", "mongodb").
    engine_type:
        Key into the internal registry (e.g. "postgres", "mongodb").
    connection_params:
        Dict with host, port, user, password, dbname, etc.
    """
    cls = _REGISTRY.get(engine_type)
    if cls is None:
        raise ValueError(
            f"Unknown engine_type '{engine_type}'. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return cls(engine_name=engine_name, connection_params=connection_params)

