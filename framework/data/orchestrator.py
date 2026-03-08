"""
DataOrchestrator – Schema creation, deterministic seeding, index warm-up.

Translates the engine-agnostic schema definition from config.yaml into
concrete DDL (PostgreSQL) or collection + index setup (MongoDB) and then
bulk-loads deterministically generated rows / documents.
"""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any, Dict, List

from faker import Faker

from framework.drivers.base import DatabaseDriverInterface

logger = logging.getLogger(__name__)

# ---- type-mapping helpers ------------------------------------------------

_PG_TYPE_MAP = {
    "integer": "INTEGER",
    "varchar": "VARCHAR",
    "float": "DOUBLE PRECISION",
    "timestamp": "TIMESTAMPTZ",
    "text": "TEXT",
    "boolean": "BOOLEAN",
}


def _pg_col_def(col: Dict[str, Any]) -> str:
    """Build a single PostgreSQL column definition string."""
    pg_type = _PG_TYPE_MAP.get(col["type"], "TEXT")
    if col["type"] == "varchar" and "length" in col:
        pg_type = f"VARCHAR({col['length']})"
    parts = [col["name"], pg_type]
    if col.get("primary_key"):
        parts.append("PRIMARY KEY")
    return " ".join(parts)


# ---- main class -----------------------------------------------------------


class DataOrchestrator:
    """Creates schemas, seeds data, and warms up indexes."""

    def __init__(
        self,
        driver: DatabaseDriverInterface,
        engine_type: str,
        schema_cfg: Dict[str, Any],
        seeding_cfg: Dict[str, int],
        seed: int = 42,
    ) -> None:
        self.driver = driver
        self.engine_type = engine_type
        self.schema_cfg = schema_cfg
        self.seeding_cfg = seeding_cfg
        self.faker = Faker()
        Faker.seed(seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def setup(self) -> None:
        """Full setup: create schema → seed data → warm-up."""
        self.create_schema()
        self.seed_data()
        self.warmup_indexes()

    # ------------------------------------------------------------------
    # Schema creation
    # ------------------------------------------------------------------
    def create_schema(self) -> None:
        tables: List[Dict[str, Any]] = self.schema_cfg.get("tables", [])
        if self.engine_type == "postgres":
            self._create_schema_postgres(tables)
        elif self.engine_type == "mongodb":
            self._create_schema_mongo(tables)
        else:
            raise ValueError(f"Unsupported engine_type: {self.engine_type}")

    def _create_schema_postgres(self, tables: List[Dict[str, Any]]) -> None:
        for tbl in tables:
            cols = ", ".join(_pg_col_def(c) for c in tbl["columns"])
            ddl = f'CREATE TABLE IF NOT EXISTS {tbl["name"]} ({cols});'
            self.driver.execute(ddl)
            logger.info("PG table created: %s", tbl["name"])

            for idx in tbl.get("indexes", []):
                idx_cols = ", ".join(idx["columns"])
                idx_name = f'idx_{tbl["name"]}_{"_".join(idx["columns"])}'
                unique = "UNIQUE " if idx.get("unique") else ""
                self.driver.execute(
                    f"CREATE {unique}INDEX IF NOT EXISTS {idx_name} "
                    f'ON {tbl["name"]} ({idx_cols});'
                )
                logger.info("PG index created: %s", idx_name)

    def _create_schema_mongo(self, tables: List[Dict[str, Any]]) -> None:
        for tbl in tables:
            col_name = tbl["name"]
            # Ensure collection exists
            self.driver.execute(lambda db, cn=col_name: db.create_collection(cn) if cn not in db.list_collection_names() else None)
            logger.info("Mongo collection ensured: %s", col_name)

            for idx in tbl.get("indexes", []):
                keys = [(c, 1) for c in idx["columns"]]
                unique = idx.get("unique", False)
                self.driver.execute(
                    lambda db, cn=col_name, k=keys, u=unique: db[cn].create_index(k, unique=u)
                )
                logger.info("Mongo index created on %s: %s", col_name, idx["columns"])

    # ------------------------------------------------------------------
    # Deterministic data seeding
    # ------------------------------------------------------------------
    def seed_data(self) -> None:
        for table_name, count in self.seeding_cfg.items():
            rows = self._generate_rows(table_name, count)
            if self.engine_type == "postgres":
                self._seed_postgres(table_name, rows)
            elif self.engine_type == "mongodb":
                self._seed_mongo(table_name, rows)
            logger.info("Seeded %d rows into %s", count, table_name)

    def _generate_rows(self, table_name: str, count: int) -> List[Dict[str, Any]]:
        """Generate *count* deterministic rows for *table_name*."""
        generators = {
            "users": self._gen_user,
            "orders": self._gen_order,
        }
        gen = generators.get(table_name)
        if gen is None:
            raise ValueError(f"No generator defined for table '{table_name}'")
        return [gen(i) for i in range(1, count + 1)]

    def _gen_user(self, i: int) -> Dict[str, Any]:
        return {
            "id": i,
            "username": self.faker.unique.user_name(),
            "email": self.faker.unique.email(),
            "created_at": self.faker.date_time_between(
                start_date="-2y", end_date="now", tzinfo=timezone.utc,
            ),
        }

    def _gen_order(self, i: int) -> Dict[str, Any]:
        return {
            "id": i,
            "user_id": self.faker.random_int(min=1, max=self.seeding_cfg.get("users", 1000)),
            "product": self.faker.catch_phrase(),
            "quantity": self.faker.random_int(min=1, max=100),
            "price": round(self.faker.pyfloat(min_value=0.99, max_value=999.99, right_digits=2), 2),
            "ordered_at": self.faker.date_time_between(
                start_date="-1y", end_date="now", tzinfo=timezone.utc,
            ),
        }

    # ---- Postgres bulk insert ----
    def _seed_postgres(self, table_name: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        cols_str = ", ".join(columns)
        placeholders = ", ".join(f"%({c})s" for c in columns)
        sql = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"
        self.driver.execute_many(sql, rows)

    # ---- Mongo bulk insert ----
    def _seed_mongo(self, table_name: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        self.driver.execute(
            lambda db, tn=table_name, r=rows: db[tn].insert_many(r)
        )

    # ------------------------------------------------------------------
    # Index warm-up
    # ------------------------------------------------------------------
    def warmup_indexes(self) -> None:
        """Run lightweight queries to force the engine to cache indexes."""
        if self.engine_type == "postgres":
            for tbl in self.schema_cfg.get("tables", []):
                self.driver.execute(
                    f'SELECT count(*) FROM {tbl["name"]};'
                )
                for idx in tbl.get("indexes", []):
                    col = idx["columns"][0]
                    self.driver.execute(
                        f'SELECT * FROM {tbl["name"]} ORDER BY {col} LIMIT 10;'
                    )
        elif self.engine_type == "mongodb":
            for tbl in self.schema_cfg.get("tables", []):
                cn = tbl["name"]
                self.driver.execute(lambda db, c=cn: db[c].estimated_document_count())
                for idx in tbl.get("indexes", []):
                    col = idx["columns"][0]
                    self.driver.execute(
                        lambda db, c=cn, cl=col: list(db[c].find().sort(cl, 1).limit(10))
                    )
        logger.info("Index warm-up complete")

