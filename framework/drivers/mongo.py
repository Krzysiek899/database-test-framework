"""
MongoDB driver – concrete implementation of DatabaseDriverInterface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from pymongo import MongoClient

from framework.drivers.base import DatabaseDriverInterface
from framework.reporting.explain_logger import ExplainLogger

logger = logging.getLogger(__name__)


class MongoDriver(DatabaseDriverInterface):
    """MongoDB driver backed by pymongo."""

    def __init__(self, engine_name: str, connection_params: Dict[str, Any]) -> None:
        super().__init__(engine_name, connection_params)
        self._client: Optional[MongoClient] = None
        self._db: Any = None
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._explain_logger = ExplainLogger("mongodb", self.run_timestamp)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
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
        self._client.admin.command("ping")
        logger.info("Connected to MongoDB on port %s", port)

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.close()
            logger.info("Disconnected from MongoDB")

    def create_schema(self, table_defs: List[Dict[str, Any]]) -> None:
        pass

    def create_index(self, table_name: str, column_name: str, **kwargs) -> None:
        """Create index on given column. Supports unique=True for unique indices."""
        if self._db is None:
            logger.warning("Not connected to MongoDB. Skipping index creation.")
            return
        
        unique = kwargs.get("unique", False)
        try:
            self._db[table_name].create_index(column_name, unique=unique)
            logger.info("Created %s index on %s.%s", "unique" if unique else "regular", table_name, column_name)
        except Exception as e:
            logger.warning("Failed to create index on %s.%s: %s", table_name, column_name, e)

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
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

    def select(self, table_name: str, filter: Dict, use_explain: bool = False, explain_context: str = None) -> Any:
        cursor = self._db[table_name].find(filter)
        if use_explain:
            explain_output = cursor.explain()
            self._explain_logger.log(
                explain_lines=[str(explain_output)],
                table_name=table_name,
                filter_repr=filter,
                context=explain_context,
            )
        return list(cursor)

    def find_all(self, table_name: str) -> Any:
        return list(self._db[table_name].find())

    def count(self, table_name: str, filter: Optional[Dict] = None) -> int:
        return self._db[table_name].count_documents(filter or {})

    def select_advanced(self, table_name: str, filters: Optional[Dict] = None,
                       joins: Optional[List[tuple]] = None, group_by: Optional[List[str]] = None,
                       order_by: Optional[List[tuple]] = None, limit: Optional[int] = None,
                       offset: Optional[int] = None, use_explain: bool = False) -> Any:
        """Advanced SELECT with aggregation pipeline support (JOIN-like $lookup, GROUP BY, ORDER BY, LIMIT).
        
        Args:
            table_name: Collection name
            filters: $match conditions (supports range filters)
            joins: List of tuples for $lookup: [(left_coll, right_coll, left_col, right_col), ...]
            group_by: List of field names to GROUP BY
            order_by: List of tuples: [("field", "asc"/"desc"), ...]
            limit: LIMIT clause
            offset: OFFSET clause (requires limit)
            use_explain: Log explain output
        
        Returns:
            List of result documents
        """
        pipeline = []
        
        # Stage 1: $match (filters)
        if filters:
            match_stage = {}
            for k, v in filters.items():
                if isinstance(v, dict) and any(op in v for op in ["gt", "lt", "gte", "lte", "in"]):
                    # Range filter
                    mongo_filter = {}
                    for op, val in v.items():
                        if op == "gt":
                            mongo_filter["$gt"] = val
                        elif op == "lt":
                            mongo_filter["$lt"] = val
                        elif op == "gte":
                            mongo_filter["$gte"] = val
                        elif op == "lte":
                            mongo_filter["$lte"] = val
                        elif op == "in":
                            mongo_filter["$in"] = val
                    match_stage[k] = mongo_filter
                else:
                    match_stage[k] = v
            if match_stage:
                pipeline.append({"$match": match_stage})
        
        # Stage 2: $lookup (JOINs)
        if joins:
            for left_coll, right_coll, left_col, right_col in joins:
                pipeline.append({
                    "$lookup": {
                        "from": right_coll,
                        "localField": left_col,
                        "foreignField": right_col,
                        "as": f"{right_coll}_joined"
                    }
                })
        
        # Stage 3: $group (GROUP BY)
        if group_by:
            group_stage = {"_id": {}}
            for col in group_by:
                group_stage["_id"][col] = f"${col}"
            pipeline.append({"$group": group_stage})
        
        # Stage 4: $sort (ORDER BY)
        if order_by:
            sort_stage = {}
            for col_name, direction in order_by:
                sort_stage[col_name] = -1 if direction.lower() == "desc" else 1
            if sort_stage:
                pipeline.append({"$sort": sort_stage})
        
        # Stage 5: $skip (OFFSET)
        if offset is not None:
            pipeline.append({"$skip": offset})
        
        # Stage 6: $limit (LIMIT)
        if limit is not None:
            pipeline.append({"$limit": limit})
        
        if use_explain:
            os.makedirs("results/explain_logs", exist_ok=True)
            log_path = f"results/explain_logs/mongodb_{self.run_timestamp}.txt"
            
            with open(log_path, "a") as f:
                f.write(f"--- EXPLAIN TARGET: {table_name} (advanced) ---\n")
                f.write(f"Pipeline: {pipeline}\n")
                f.write("\n")
        
        results = list(self._db[table_name].aggregate(pipeline))
        return results

    def select_aggregation(self, table_name: str, filters: Optional[Dict] = None,
                          group_by: Optional[List[str]] = None,
                          aggregates: Optional[Dict[str, tuple]] = None,
                          order_by: Optional[List[tuple]] = None, limit: Optional[int] = None,
                          use_explain: bool = False) -> Any:
        """SELECT with aggregation (COUNT, AVG, SUM, MIN, MAX) via aggregation pipeline.
        
        Args:
            table_name: Collection name
            filters: $match conditions
            group_by: List of field names to GROUP BY
            aggregates: Dict of {alias: (field, func_name)}
                       Example: {"total": ("amount", "sum"), "avg_score": ("score", "avg")}
            order_by: List of tuples: [("field", "asc"/"desc"), ...]
            limit: LIMIT clause
            use_explain: Log explain output
        
        Returns:
            List of aggregated documents
        """
        pipeline = []
        
        # Stage 1: $match (filters)
        if filters:
            match_stage = {}
            for k, v in filters.items():
                if isinstance(v, dict) and any(op in v for op in ["gt", "lt", "gte", "lte", "in"]):
                    mongo_filter = {}
                    for op, val in v.items():
                        if op == "gt":
                            mongo_filter["$gt"] = val
                        elif op == "lt":
                            mongo_filter["$lt"] = val
                        elif op == "gte":
                            mongo_filter["$gte"] = val
                        elif op == "lte":
                            mongo_filter["$lte"] = val
                        elif op == "in":
                            mongo_filter["$in"] = val
                    match_stage[k] = mongo_filter
                else:
                    match_stage[k] = v
            if match_stage:
                pipeline.append({"$match": match_stage})
        
        # Stage 2: $group with aggregates
        if group_by or aggregates:
            group_stage = {"_id": {}}
            
            # Add GROUP BY fields
            if group_by:
                for col in group_by:
                    group_stage["_id"][col] = f"${col}"
            
            # Add aggregates
            if aggregates:
                for alias, (field, agg_func) in aggregates.items():
                    func_map = {
                        "count": "$sum",
                        "sum": "$sum",
                        "avg": "$avg",
                        "min": "$min",
                        "max": "$max"
                    }
                    
                    if agg_func.lower() == "count":
                        group_stage[alias] = {"$sum": 1}
                    elif agg_func.lower() in func_map:
                        op = func_map[agg_func.lower()]
                        group_stage[alias] = {op: f"${field}"}
            
            if group_stage:
                pipeline.append({"$group": group_stage})
        
        # Stage 3: $sort (ORDER BY)
        if order_by:
            sort_stage = {}
            for col_name, direction in order_by:
                sort_stage[col_name] = -1 if direction.lower() == "desc" else 1
            if sort_stage:
                pipeline.append({"$sort": sort_stage})
        
        # Stage 4: $limit (LIMIT)
        if limit is not None:
            pipeline.append({"$limit": limit})
        
        if use_explain:
            os.makedirs("results/explain_logs", exist_ok=True)
            log_path = f"results/explain_logs/mongodb_{self.run_timestamp}.txt"
            
            with open(log_path, "a") as f:
                f.write(f"--- EXPLAIN TARGET: {table_name} (aggregation) ---\n")
                f.write(f"Pipeline: {pipeline}\n")
                f.write("\n")
        
        results = list(self._db[table_name].aggregate(pipeline))
        return results

