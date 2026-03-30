"""
DriverFactory – Factory Pattern for instantiating the correct driver.
"""

from __future__ import annotations

from typing import Any, Dict

from framework.drivers.base import DatabaseDriverInterface

_REGISTRY: Dict[str, type] = {
    "postgres": "framework.drivers.postgres.PostgresDriver",
    "mongodb": "framework.drivers.mongo.MongoDriver",
    "mysql": "framework.drivers.mysql.MysqlDriver",
    "couchdb": "framework.drivers.couchdb.CouchDbDriver",
}


def create_driver(
    engine_name: str, engine_type: str, connection_params: Dict[str, Any]
) -> "DatabaseDriverInterface":
    if engine_type == "postgres":
        from framework.drivers.postgres import PostgresDriver

        return PostgresDriver(engine_name, connection_params)
    elif engine_type == "mongodb":
        from framework.drivers.mongo import MongoDriver

        return MongoDriver(engine_name, connection_params)
    elif engine_type == "mysql":
        from framework.drivers.mysql import MysqlDriver

        return MysqlDriver(engine_name, connection_params)
    elif engine_type == "couchdb":
        from framework.drivers.couchdb import CouchDbDriver

        return CouchDbDriver(engine_name, connection_params)
    else:
        raise ValueError(f"Unsupported engine_type: {engine_type}")
