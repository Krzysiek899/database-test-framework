"""
Relational Database Mapper using SQLAlchemy Core.
Handles schema creation and query generation for relational databases.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

from sqlalchemy import MetaData, Table as SATable, Column, Integer, String, Float, DateTime, Boolean, ForeignKey, select, func, and_, or_, Index
from sqlalchemy.sql import text
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
        self._list_fields = {}
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

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

    def create_index(self, table_name: str, column_name: str, **kwargs) -> None:
        if table_name not in self.metadata.tables:
            logger.warning("Table %s not found. Skipping index creation.", table_name)
            return

        table = self.metadata.tables[table_name]

        if column_name not in table.c:
            logger.warning("Column %s not found in table %s. Skipping index creation.", column_name, table_name)
            return

        unique = kwargs.get("unique", False)
        idx = Index(f"ix_{table_name}_{column_name}", table.c[column_name], unique=unique)
        if self.engine:
            idx.create(self.engine)
            logger.info("Created %s index on %s.%s", "unique" if unique else "regular", table_name, column_name)

    def _build_where_clause(self, table, filter_dict: Dict):
        """Build WHERE clause supporting: equality, range filters (gt/lt/gte/lte), LIKE, IN operators.
        
        Supports both simple column names and qualified names:
        - {"amount": 100}  # simple
        - {"enrollments.user_id": 5}  # qualified (for JOINed tables)
        - {"amount": {"gt": 50, "lt": 200}}  # range
        """
        conditions = []
        for k, v in filter_dict.items():
            # Resolve column reference (either simple or qualified)
            col = None
            if "." in k:
                # Qualified name: "table.column"
                table_name_qual, col_name = k.split(".", 1)
                tbl = self.metadata.tables.get(table_name_qual)
                if tbl is not None and hasattr(tbl.c, col_name):
                    col = getattr(tbl.c, col_name)
            else:
                # Simple name: "column"
                if hasattr(table.c, k):
                    col = getattr(table.c, k)
            
            if col is None:
                continue
            
            # Range filter: {"amount": {"gt": 50, "lt": 200}}
            if isinstance(v, dict) and any(op in v for op in ["gt", "lt", "gte", "lte", "in", "like"]):
                for op, val in v.items():
                    if op == "gt":
                        conditions.append(col > val)
                    elif op == "lt":
                        conditions.append(col < val)
                    elif op == "gte":
                        conditions.append(col >= val)
                    elif op == "lte":
                        conditions.append(col <= val)
                    elif op == "in":
                        conditions.append(col.in_(val))
                    elif op == "like":
                        conditions.append(col.like(val))
            # Standard equality
            else:
                conditions.append(col == v)
        
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

    def select(self, table_name: str, filter: Dict, use_explain: bool = False) -> Any:
        table = self.metadata.tables[table_name]
        where_clause = self._build_where_clause(table, filter)
        stmt = select(table).where(where_clause)

        if use_explain:
            compiled = stmt.compile(self.engine, compile_kwargs={"literal_binds": True})
            explain_query = f"EXPLAIN {compiled.string}"
            explain_result = self._connection.execute(text(explain_query)).fetchall()

            os.makedirs("results/explain_logs", exist_ok=True)
            db_name = self.engine.name if self.engine else "sql"
            log_path = f"results/explain_logs/{db_name}_{self.run_timestamp}.txt"

            with open(log_path, "a") as f:
                f.write(f"--- EXPLAIN TARGET: {table_name} filter: {filter} ---\n")
                f.write(f"Query: {explain_query}\n")
                for row in explain_result:
                    f.write(f"{row}\n")

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

    def select_advanced(self, table_name: str, filters: Optional[Dict] = None, 
                       joins: Optional[List[tuple]] = None, group_by: Optional[List[str]] = None,
                       order_by: Optional[List[tuple]] = None, limit: Optional[int] = None,
                       offset: Optional[int] = None, use_explain: bool = False) -> Any:
        """Advanced SELECT with JOIN, GROUP BY, ORDER BY, LIMIT, OFFSET support.
        
        Fully SQLAlchemy Core native - all filtering, joining, grouping, ordering happens at DB level.
        
        Args:
            table_name: Primary table to select from
            filters: WHERE conditions (supports qualified names: "table.column", range filters: {"col": {"gt": 5, "lt": 10}})
            joins: List of tuples: [(left_table, right_table, left_col, right_col), ...]
            group_by: List of column names to GROUP BY (supports qualified names: "table.column")
            order_by: List of tuples: [("col_name", "asc"/"desc"), ...] (supports qualified names)
            limit: LIMIT clause
            offset: OFFSET clause
            use_explain: Log EXPLAIN output
        
        Returns:
            List of dicts with result rows
        """
        primary_table = self.metadata.tables[table_name]
        joined_tables = set()
        
        # Start with SELECT from primary table
        stmt = select(primary_table)
        
        # Apply JOINs first (before WHERE) to enable qualified column references
        if joins:
            for left_tbl_name, right_tbl_name, left_col, right_col in joins:
                left_tbl = self.metadata.tables.get(left_tbl_name)
                right_tbl = self.metadata.tables.get(right_tbl_name)
                
                if left_tbl is not None and right_tbl is not None:
                    if hasattr(left_tbl.c, left_col) and hasattr(right_tbl.c, right_col):
                        stmt = stmt.join(
                            right_tbl,
                            getattr(left_tbl.c, left_col) == getattr(right_tbl.c, right_col)
                        )
                        joined_tables.add(right_tbl_name)
        
        # Apply WHERE filters (supports qualified column names from joined tables)
        if filters:
            where_conditions = []
            for k, v in filters.items():
                col = None
                # Resolve qualified or simple column names
                if "." in k:
                    table_qual, col_name = k.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_name):
                        col = getattr(tbl.c, col_name)
                else:
                    if hasattr(primary_table.c, k):
                        col = getattr(primary_table.c, k)
                
                if col is None:
                    continue
                
                # Handle range filters and operators
                if isinstance(v, dict) and any(op in v for op in ["gt", "lt", "gte", "lte", "in", "like"]):
                    for op, val in v.items():
                        if op == "gt":
                            where_conditions.append(col > val)
                        elif op == "lt":
                            where_conditions.append(col < val)
                        elif op == "gte":
                            where_conditions.append(col >= val)
                        elif op == "lte":
                            where_conditions.append(col <= val)
                        elif op == "in":
                            where_conditions.append(col.in_(val))
                        elif op == "like":
                            where_conditions.append(col.like(val))
                else:
                    where_conditions.append(col == v)
            
            if where_conditions:
                stmt = stmt.where(and_(*where_conditions))
        
        # Apply GROUP BY (supports qualified column names)
        if group_by:
            group_cols = []
            for col_name in group_by:
                col = None
                if "." in col_name:
                    table_qual, col_qual = col_name.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_qual):
                        col = getattr(tbl.c, col_qual)
                else:
                    if hasattr(primary_table.c, col_name):
                        col = getattr(primary_table.c, col_name)
                
                if col is not None:
                    group_cols.append(col)
            
            if group_cols:
                stmt = stmt.group_by(*group_cols)
        
        # Apply ORDER BY (supports qualified column names)
        if order_by:
            order_cols = []
            for col_name, direction in order_by:
                col = None
                if "." in col_name:
                    table_qual, col_qual = col_name.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_qual):
                        col = getattr(tbl.c, col_qual)
                else:
                    if hasattr(primary_table.c, col_name):
                        col = getattr(primary_table.c, col_name)
                
                if col is not None:
                    order_cols.append(col.desc() if direction.lower() == "desc" else col.asc())
            
            if order_cols:
                stmt = stmt.order_by(*order_cols)
        
        # Apply LIMIT/OFFSET
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        
        # EXPLAIN logging
        if use_explain:
            try:
                compiled = stmt.compile(self.engine, compile_kwargs={"literal_binds": True})
                explain_query = f"EXPLAIN {compiled.string}"
                explain_result = self._connection.execute(text(explain_query)).fetchall()
                
                os.makedirs("results/explain_logs", exist_ok=True)
                db_name = self.engine.name if self.engine else "sql"
                log_path = f"results/explain_logs/{db_name}_{self.run_timestamp}.txt"
                
                with open(log_path, "a") as f:
                    f.write(f"--- EXPLAIN TARGET: {table_name} (advanced) filters: {filters} joins: {joins} ---\n")
                    f.write(f"Query: {explain_query}\n")
                    for row in explain_result:
                        f.write(f"{row}\n")
                    f.write("\n")
            except Exception as e:
                logger.warning("EXPLAIN failed: %s", str(e))
        
        # Execute query - all logic at database level
        rows = self._connection.execute(stmt).fetchall()
        
        # Convert rows to dicts (minimal Python processing)
        results = []
        for row in rows:
            row_dict = dict(row._mapping)  # type: ignore
            results.append(row_dict)
        
        return results

    def select_aggregation(self, table_name: str, filters: Optional[Dict] = None,
                          group_by: Optional[List[str]] = None, 
                          aggregates: Optional[Dict[str, tuple]] = None,
                          order_by: Optional[List[tuple]] = None, limit: Optional[int] = None,
                          use_explain: bool = False) -> Any:
        """SELECT with aggregation (COUNT, AVG, SUM, MIN, MAX) - fully database-side.
        
        Builds proper SQLAlchemy aggregate query using func.count(), func.sum(), etc.
        All logic executed at database level.
        
        Args:
            table_name: Table to aggregate from
            filters: WHERE conditions (supports qualified names and range filters)
            group_by: List of column names to GROUP BY (supports qualified names: "table.column")
            aggregates: Dict of {alias: (column, func_name)}
                       Example: {"total": ("amount", "sum"), "avg_score": ("score", "avg")}
            order_by: List of tuples: [("col_name", "asc"/"desc"), ...] (supports qualified names and aliases)
            limit: LIMIT clause
            use_explain: Log EXPLAIN output
        
        Returns:
            List of dicts with aggregated results
        """
        table = self.metadata.tables[table_name]
        
        # Build SELECT clause with GROUP BY columns + aggregates
        select_cols = []
        agg_functions = {
            "count": func.count,
            "sum": func.sum,
            "avg": func.avg,
            "min": func.min,
            "max": func.max
        }
        
        # Add GROUP BY columns to SELECT
        if group_by:
            for col_name in group_by:
                col = None
                if "." in col_name:
                    table_qual, col_qual = col_name.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_qual):
                        col = getattr(tbl.c, col_qual)
                else:
                    if hasattr(table.c, col_name):
                        col = getattr(table.c, col_name)
                
                if col is not None:
                    select_cols.append(col)
        
        # Add aggregates to SELECT
        if aggregates:
            for alias, (col_name, agg_func) in aggregates.items():
                col = None
                if "." in col_name:
                    table_qual, col_qual = col_name.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_qual):
                        col = getattr(tbl.c, col_qual)
                else:
                    if hasattr(table.c, col_name):
                        col = getattr(table.c, col_name)
                
                if col is not None and agg_func.lower() in agg_functions:
                    agg_col = agg_functions[agg_func.lower()](col).label(alias)
                    select_cols.append(agg_col)
        
        if not select_cols:
            return []
        
        # Build query: SELECT ... FROM ... WHERE ... GROUP BY ... ORDER BY ... LIMIT
        stmt = select(*select_cols).select_from(table)
        
        # Apply WHERE filters
        if filters:
            where_conditions = []
            for k, v in filters.items():
                col = None
                if "." in k:
                    table_qual, col_name = k.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_name):
                        col = getattr(tbl.c, col_name)
                else:
                    if hasattr(table.c, k):
                        col = getattr(table.c, k)
                
                if col is None:
                    continue
                
                # Handle range filters
                if isinstance(v, dict) and any(op in v for op in ["gt", "lt", "gte", "lte", "in", "like"]):
                    for op, val in v.items():
                        if op == "gt":
                            where_conditions.append(col > val)
                        elif op == "lt":
                            where_conditions.append(col < val)
                        elif op == "gte":
                            where_conditions.append(col >= val)
                        elif op == "lte":
                            where_conditions.append(col <= val)
                        elif op == "in":
                            where_conditions.append(col.in_(val))
                        elif op == "like":
                            where_conditions.append(col.like(val))
                else:
                    where_conditions.append(col == v)
            
            if where_conditions:
                stmt = stmt.where(and_(*where_conditions))
        
        # Apply GROUP BY
        if group_by:
            group_cols = []
            for col_name in group_by:
                col = None
                if "." in col_name:
                    table_qual, col_qual = col_name.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_qual):
                        col = getattr(tbl.c, col_qual)
                else:
                    if hasattr(table.c, col_name):
                        col = getattr(table.c, col_name)
                
                if col is not None:
                    group_cols.append(col)
            
            if group_cols:
                stmt = stmt.group_by(*group_cols)
        
        # Apply ORDER BY (can be on GROUP BY columns or aggregate aliases)
        if order_by:
            order_clauses = []
            for col_name, direction in order_by:
                col = None
                
                # Try to resolve as regular column first
                if "." in col_name:
                    table_qual, col_qual = col_name.split(".", 1)
                    tbl = self.metadata.tables.get(table_qual)
                    if tbl is not None and hasattr(tbl.c, col_qual):
                        col = getattr(tbl.c, col_qual)
                else:
                    if hasattr(table.c, col_name):
                        col = getattr(table.c, col_name)
                
                # If not found, assume it's an aggregate alias
                if col is None:
                    col = col_name
                
                if isinstance(col, str):
                    # Alias - use text() for ORDER BY
                    order_clauses.append(text(f"{col} {direction.upper()}"))
                else:
                    # Column object
                    order_clauses.append(col.desc() if direction.lower() == "desc" else col.asc())
            
            if order_clauses:
                stmt = stmt.order_by(*order_clauses)
        
        # Apply LIMIT
        if limit is not None:
            stmt = stmt.limit(limit)
        
        # EXPLAIN logging
        if use_explain:
            try:
                compiled = stmt.compile(self.engine, compile_kwargs={"literal_binds": True})
                explain_query = f"EXPLAIN {compiled.string}"
                explain_result = self._connection.execute(text(explain_query)).fetchall()
                
                os.makedirs("results/explain_logs", exist_ok=True)
                db_name = self.engine.name if self.engine else "sql"
                log_path = f"results/explain_logs/{db_name}_{self.run_timestamp}.txt"
                
                with open(log_path, "a") as f:
                    f.write(f"--- EXPLAIN TARGET: {table_name} (aggregation) group_by: {group_by} ---\n")
                    f.write(f"Query: {explain_query}\n")
                    for row in explain_result:
                        f.write(f"{row}\n")
                    f.write("\n")
            except Exception as e:
                logger.warning("EXPLAIN failed: %s", str(e))
        
        # Execute - all logic at database level
        rows = self._connection.execute(stmt).fetchall()
        
        # Minimal Python processing - just convert to dicts
        results = []
        for row in rows:
            row_dict = dict(row._mapping)  # type: ignore
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
