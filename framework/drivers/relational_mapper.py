"""
Relational Database Mapper using SQLAlchemy Core.
Handles schema creation and query generation for relational databases.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlalchemy import MetaData, Table as SATable, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, select, func, and_, Index
from pydantic import BaseModel

logger = logging.getLogger(__name__)

def _map_type(python_type: Any) -> Any:
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

def _is_list_type(python_type: Any) -> bool:
    if hasattr(python_type, "__origin__") and python_type.__origin__ is list:
        return True
    return False

def _get_list_inner_type(python_type: Any) -> Any:
    if hasattr(python_type, "__args__") and python_type.__args__:
        return python_type.__args__[0]
    return str

class RelationalMapper:
    def __init__(self, metadata: MetaData = None):
        self.metadata = metadata if metadata is not None else MetaData()
        self.engine = None
        self._connection = None
        self._list_fields = {} # table_name -> dict of list fields {field_name: inner_type}

    def set_engine_and_connection(self, engine: Any, connection: Any):
        self.engine = engine
        self._connection = connection

    def create_schema(self, table_defs: List[Dict[str, Any]]) -> None:
        for table_def in table_defs:
            table_name = table_def["name"]
            columns = []
            list_fields = {}

            for col in table_def["columns"]:
                py_type = col["python_type"]

                if _is_list_type(py_type):
                    list_fields[col["name"]] = _get_list_inner_type(py_type)
                    continue

                columns.append(
                    Column(
                        col["name"],
                        _map_type(py_type),
                        primary_key=col["primary_key"],
                        nullable=col["nullable"]
                    )
                )

            SATable(table_name, self.metadata, *columns)
            self._list_fields[table_name] = list_fields

            pk_col = next((c["name"] for c in table_def["columns"] if c.get("primary_key")), "id")

            for field_name, inner_type in list_fields.items():
                assoc_table_name = f"{table_name}_{field_name}"
                SATable(
                    assoc_table_name,
                    self.metadata,
                    Column("id", Integer, primary_key=True, autoincrement=True),
                    Column(f"{table_name}_id", Integer, ForeignKey(f"{table_name}.{pk_col}", ondelete="CASCADE")),
                    Column("value", _map_type(inner_type), nullable=False)
                )

        if self.engine:
            self.metadata.drop_all(self.engine)
            self.metadata.create_all(self.engine)
            logger.info("Recreated schema with SQLAlchemy Core")

    def create_index(self, table_name: str, column_name: str) -> None:
        if table_name not in self.metadata.tables:
            logger.warning("Table %s not found. Skipping index creation.", table_name)
            return

        table = self.metadata.tables[table_name]

        if column_name not in table.c:
            logger.warning("Column %s not found in table %s. Skipping index creation.", column_name, table_name)
            return

        idx = Index(f"ix_{table_name}_{column_name}", table.c[column_name])
        idx.create(self.engine)

    def _build_where_clause(self, table, filter_dict: Dict):
        conditions = []
        for k, v in filter_dict.items():
            if hasattr(table.c, k):
                conditions.append(getattr(table.c, k) == v)
        if not conditions:
            return True
        return and_(*conditions)

    def insert(self, table_name: str, entity: BaseModel) -> Any:
        table = self.metadata.tables[table_name]
        data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)

        assoc_data = {}
        if table_name in self._list_fields:
            for field_name in self._list_fields[table_name]:
                if field_name in data:
                    assoc_data[field_name] = data.pop(field_name)

        clean_data = {k: v for k, v in data.items() if not isinstance(v, (dict, list))}

        res = self._connection.execute(table.insert().values(**clean_data))
        inserted_id = clean_data.get('id', res.inserted_primary_key[0] if res.inserted_primary_key else None)

        if inserted_id is not None:
            for field_name, values in assoc_data.items():
                if not values:
                    continue
                assoc_table = self.metadata.tables[f"{table_name}_{field_name}"]
                assoc_insert_data = [{f"{table_name}_id": inserted_id, "value": v} for v in values]
                self._connection.execute(assoc_table.insert(), assoc_insert_data)

        return res

    def insert_many(self, table_name: str, entities: List[Any]) -> Any:
        if not entities:
            return True

        table = self.metadata.tables[table_name]
        has_lists = bool(self._list_fields.get(table_name))

        if not has_lists:
            data_list = []
            for entity in entities:
                data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
                data_list.append({k: v for k, v in data.items() if not isinstance(v, (dict, list))})
            self._connection.execute(table.insert(), data_list)
            return True

        assoc_inserts = {field: [] for field in self._list_fields[table_name]}

        for entity in entities:
            data = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
            clean_data = {k: v for k, v in data.items() if not isinstance(v, (dict, list))}

            res = self._connection.execute(table.insert().values(**clean_data))
            inserted_id = clean_data.get('id', res.inserted_primary_key[0] if res.inserted_primary_key else None)

            if inserted_id is not None:
                for field_name in self._list_fields[table_name]:
                    if field_name in data and data[field_name]:
                        for val in data[field_name]:
                            assoc_inserts[field_name].append({f"{table_name}_id": inserted_id, "value": val})

        for field_name, rows in assoc_inserts.items():
            if rows:
                assoc_table = self.metadata.tables[f"{table_name}_{field_name}"]
                self._connection.execute(assoc_table.insert(), rows)

        return True

    def update(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        table = self.metadata.tables[table_name]

        list_updates = {}
        for field in self._list_fields.get(table_name, {}):
            if field in update_data:
                list_updates[field] = update_data[field]

        clean_update = {k: v for k, v in update_data.items() if k not in self._list_fields.get(table_name, {}) and not isinstance(v, (dict, list))}

        where_clause = self._build_where_clause(table, filter)
        res = None
        if clean_update:
            stmt = table.update().where(where_clause).values(**clean_update)
            res = self._connection.execute(stmt)

        if list_updates:
            sel_stmt = select(table.c.id).where(where_clause)
            matching_ids = [r[0] for r in self._connection.execute(sel_stmt).fetchall()]

            if matching_ids:
                for field_name, new_values in list_updates.items():
                    assoc_table = self.metadata.tables[f"{table_name}_{field_name}"]
                    assoc_fk = getattr(assoc_table.c, f"{table_name}_id")

                    self._connection.execute(assoc_table.delete().where(assoc_fk.in_(matching_ids)))

                    if new_values:
                        assoc_rows = []
                        for row_id in matching_ids:
                            for val in new_values:
                                assoc_rows.append({f"{table_name}_id": row_id, "value": val})
                        if assoc_rows:
                            self._connection.execute(assoc_table.insert(), assoc_rows)

        return res

    def update_many(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        return self.update(table_name, filter, update_data)

    def delete(self, table_name: str, filter: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = table.delete().where(where_clause)
        return self._connection.execute(stmt)

    def delete_many(self, table_name: str, filter: Dict) -> Any:
        return self.delete(table_name, filter)

    def select(self, table_name: str, filter: Dict) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = select(table).where(where_clause)
        rows = self._connection.execute(stmt).fetchall()

        results = []
        for row in rows:
            row_dict = dict(row._mapping) # type: ignore
            row_id = row_dict.get('id')

            if row_id is not None and table_name in self._list_fields:
                for field_name in self._list_fields[table_name]:
                    assoc_table_name = f"{table_name}_{field_name}"
                    if assoc_table_name in self.metadata.tables:
                        assoc_table = self.metadata.tables[assoc_table_name]
                        assoc_stmt = select(assoc_table.c.value).where(
                            getattr(assoc_table.c, f"{table_name}_id") == row_id
                        )
                        values = [r[0] for r in self._connection.execute(assoc_stmt).fetchall()]
                        row_dict[field_name] = values # type: ignore

            results.append(row_dict)

        return results

    def find_all(self, table_name: str) -> Any:
        return self.select(table_name, {})

    def count(self, table_name: str, filter: Optional[Dict] = None) -> int:
        table = self.metadata.tables[table_name]
        stmt = select(func.count()).select_from(table)
        if filter:
            where_clause = self._build_where_clause(table, filter)
            stmt = stmt.where(where_clause)
        return self._connection.execute(stmt).scalar()
