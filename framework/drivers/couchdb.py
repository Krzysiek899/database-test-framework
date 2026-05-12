"""
CouchDB driver – concrete implementation of DatabaseDriverInterface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

import couchdb

from framework.drivers.base import DatabaseDriverInterface
from framework.reporting.explain_logger import ExplainLogger

logger = logging.getLogger(__name__)


class CouchDbDriver(DatabaseDriverInterface):
    """CouchDB driver backed by couchdb-python."""

    def __init__(self, engine_name: str, connection_params: Dict[str, Any]) -> None:
        super().__init__(engine_name, connection_params)
        self._server: Optional[couchdb.Server] = None
        self._db: Any = None
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._explain_logger = ExplainLogger("couchdb", self.run_timestamp)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        p = self.connection_params
        host = p.get("host", "127.0.0.1")
        port = p.get("port", 5984)
        user = p.get("user", "bench")
        password = p.get("password", "bench")

        url = f"http://{user}:{password}@{host}:{port}/"
        self._server = couchdb.Server(url)
        logger.info("Connected to CouchDB on port %s", port)

        for sys_db in ["_users", "_replicator", "_global_changes"]:
            try:
                if sys_db not in self._server:
                    self._server.create(sys_db)
            except Exception as e:
                logger.debug("Omitted creating system DB %s (may exist or missing privileges): %s", sys_db, e)

    def disconnect(self) -> None:
        logger.info("Disconnected from CouchDB")

    def create_schema(self, table_defs: List[Dict[str, Any]]) -> None:
        for table_def in table_defs:
            table_name = table_def["name"]
            if table_name in self._server:
                del self._server[table_name]
            self._server.create(table_name)
        logger.info("Recreated Databases (tables) in CouchDB")

    def create_index(self, table_name: str, column_name: str) -> None:
        pass

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------
    def get_metrics(self) -> Dict[str, Any]:
        metrics = {}
        try:
            stats = self._server.stats()
            metrics['couchdb_httpd_requests'] = stats.get('couchdb', {}).get('httpd_request_methods', {}).get('GET', {}).get('current', 0)
            metrics['couchdb_database_reads'] = stats.get('couchdb', {}).get('database_reads', {}).get('current', 0)
        except Exception:
            pass
        return metrics

    # ------------------------------------------------------------------
    # Facade Support
    # ------------------------------------------------------------------
    def insert(self, table_name: str, entity: Any) -> Any:
        data = entity.model_dump(mode='json') if hasattr(entity, "model_dump") else dict(entity)
        if "id" in data and "_id" not in data:
            data["_id"] = str(data["id"])
        db = self._server[table_name]
        doc_id, _ = db.save(data)
        return doc_id

    def insert_many(self, table_name: str, entities: List[Any]) -> Any:
        db = self._server[table_name]
        data_list = []
        for entity in entities:
            data = entity.model_dump(mode='json') if hasattr(entity, "model_dump") else dict(entity)
            if "id" in data and "_id" not in data:
                data["_id"] = str(data["id"])
            data_list.append(data)

        batch_size = 1000
        for i in range(0, len(data_list), batch_size):
            db.update(data_list[i:i + batch_size])
        return

    def update(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        db = self._server[table_name]
        for doc in db.find({'selector': filter}):
            doc.update(update_data)
            db.save(doc)
            break

    def update_many(self, table_name: str, filter: Dict, update_data: Dict) -> Any:
        db = self._server[table_name]
        docs_to_update = []
        for doc in db.find({'selector': filter}):
            doc.update(update_data)
            docs_to_update.append(doc)

        batch_size = 1000
        for i in range(0, len(docs_to_update), batch_size):
            db.update(docs_to_update[i:i + batch_size])

    def delete(self, table_name: str, filter: Dict) -> Any:
        db = self._server[table_name]
        for doc in db.find({'selector': filter}):
            db.delete(doc)
            break

    def delete_many(self, table_name: str, filter: Dict) -> Any:
        db = self._server[table_name]
        docs_to_delete = []
        for doc in db.find({'selector': filter}):
            doc['_deleted'] = True
            docs_to_delete.append(doc)

        batch_size = 1000
        for i in range(0, len(docs_to_delete), batch_size):
            db.update(docs_to_delete[i:i + batch_size])

    def select(self, table_name: str, filter: Dict, use_explain: bool = False, explain_context: str = None) -> Any:
        db = self._server[table_name]

        if use_explain:
            try:
                explain_res = db.explain({'selector': filter})
                self._explain_logger.log(
                    explain_lines=[str(explain_res)],
                    table_name=table_name,
                    filter_repr=filter,
                    context=explain_context,
                )
            except Exception as e:
                logger.warning(f"CouchDB EXPLAIN failed: {e}")

        return list(db.find({'selector': filter}))

    def find_all(self, table_name: str) -> Any:
        db = self._server[table_name]
        return [doc for doc in db.view('_all_docs', include_docs=True)]

    def count(self, table_name: str, filter: Optional[Dict] = None) -> int:
        db = self._server[table_name]
        if filter:
            return len(list(db.find({'selector': filter})))
        return len(db)

    def select_advanced(self, table_name: str, filters: Optional[Dict] = None,
                       joins: Optional[List[tuple]] = None, group_by: Optional[List[str]] = None,
                       order_by: Optional[List[tuple]] = None, limit: Optional[int] = None,
                       offset: Optional[int] = None, use_explain: bool = False,
                       explain_context: Optional[str] = None) -> Any:
        """Advanced SELECT for CouchDB (limited support - uses Mango queries).
        
        Note: CouchDB has limited JOIN support and does NOT support dynamic ORDER BY in Mango
        without explicit pre-defined indexes. Results returned unordered.
        For full functionality, use relational databases (PostgreSQL, MySQL) or MongoDB.
        """
        db = self._server[table_name]
        selector = {}
        
        # Apply filters using Mango selector
        if filters:
            for k, v in filters.items():
                if isinstance(v, dict) and any(op in v for op in ["gt", "lt", "gte", "lte", "in"]):
                    mongo_op = {}
                    for op, val in v.items():
                        if op == "gt":
                            mongo_op["$gt"] = val
                        elif op == "lt":
                            mongo_op["$lt"] = val
                        elif op == "gte":
                            mongo_op["$gte"] = val
                        elif op == "lte":
                            mongo_op["$lte"] = val
                        elif op == "in":
                            mongo_op["$in"] = val
                    selector[k] = mongo_op
                else:
                    selector[k] = v
        
        query = {'selector': selector}
        
        if use_explain:
            try:
                explain_res = db.explain(query)
                self._explain_logger.log(
                    explain_lines=[str(explain_res),
                                   f"Note: ORDER BY not supported in CouchDB Mango without pre-defined indexes.",
                                   f"Requested: joins={joins}, group_by={group_by}, order_by={order_by}, limit={limit}, offset={offset}"],
                    table_name=table_name,
                    filter_repr={"filters": filters, "joins": joins},
                    query=str(query),
                    context=explain_context,
                )
            except Exception as e:
                logger.warning("CouchDB EXPLAIN (advanced) failed: %s", e)

        try:
            results = list(db.find(query))
            return results
        except Exception as e:
            logger.warning(f"CouchDB advanced query failed: {e}. Returning empty results.")
            return []


    def select_aggregation(self, table_name: str, filters: Optional[Dict] = None,
                          group_by: Optional[List[str]] = None,
                          aggregates: Optional[Dict[str, tuple]] = None,
                          order_by: Optional[List[tuple]] = None, limit: Optional[int] = None,
                          use_explain: bool = False,
                          explain_context: Optional[str] = None) -> Any:
        """Aggregation for CouchDB (NOT FULLY SUPPORTED - CouchDB lacks native GROUP BY).
        
        Note: CouchDB does NOT natively support GROUP BY queries in Mango.
        This implementation returns unordered, unaggregated results to avoid
        distorting performance measurements with Python-side aggregation.
        For proper aggregation benchmarking, use relational databases or MongoDB.
        """
        db = self._server[table_name]
        
        selector = {}
        if filters:
            for k, v in filters.items():
                if isinstance(v, dict) and any(op in v for op in ["gt", "lt", "gte", "lte"]):
                    mongo_op = {}
                    for op, val in v.items():
                        if op == "gt":
                            mongo_op["$gt"] = val
                        elif op == "lt":
                            mongo_op["$lt"] = val
                        elif op == "gte":
                            mongo_op["$gte"] = val
                        elif op == "lte":
                            mongo_op["$lte"] = val
                    selector[k] = mongo_op
                else:
                    selector[k] = v
        
        query = {'selector': selector}
        
        if use_explain:
            self._explain_logger.log(
                explain_lines=[f"WARNING: CouchDB does NOT support GROUP BY in Mango queries.",
                               f"Requested: group_by={group_by}, aggregates={aggregates}, order_by={order_by}, limit={limit}",
                               f"Returning raw filtered results without aggregation to preserve performance measurements."],
                table_name=table_name,
                filter_repr={"filters": filters, "group_by": group_by, "aggregates": aggregates},
                query=str(query),
                context=explain_context,
            )

        try:
            docs = list(db.find(query))
            # Do NOT aggregate in Python - that would distort benchmark results
            # CouchDB simply doesn't support this operation efficiently
            return docs
        except Exception as e:
            logger.warning(f"CouchDB aggregation query failed: {e}")
            return []

