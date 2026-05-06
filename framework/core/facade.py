from typing import Any

from pydantic import BaseModel


class CollectionFacade:
    def __init__(self, table_name: str, driver: Any):
        self.table_name = table_name
        self.driver = driver

    def create_index(self, column_name: str, **kwargs) -> None:
        return self.driver.create_index(self.table_name, column_name, **kwargs)

    def insert(self, entity: BaseModel) -> Any:
        return self.driver.insert(self.table_name, entity)

    def insert_many(self, entities: list) -> Any:
        return self.driver.insert_many(self.table_name, entities)

    def update(self, filter: dict, update_data: dict) -> Any:
        return self.driver.update(self.table_name, filter, update_data)

    def update_many(self, filter: dict, update_data: dict) -> Any:
        return self.driver.update_many(self.table_name, filter, update_data)

    def delete(self, filter: dict) -> Any:
        return self.driver.delete(self.table_name, filter)

    def delete_many(self, filter: dict) -> Any:
        return self.driver.delete_many(self.table_name, filter)

    def select(self, filter: dict, use_explain: bool = False) -> Any:
        return self.driver.select(self.table_name, filter, use_explain)

    def find_all(self) -> Any:
        return self.driver.find_all(self.table_name)

    def count(self, filter: dict = None) -> int:
        return self.driver.count(self.table_name, filter)

    def select_all(self) -> Any:
        return self.find_all()

    def select_advanced(self, filters: dict = None, joins: list = None, group_by: list = None,
                       order_by: list = None, limit: int = None, offset: int = None,
                       use_explain: bool = False) -> Any:
        """Advanced SELECT with JOIN, GROUP BY, ORDER BY, LIMIT, OFFSET support.
        
        Proxy to driver.select_advanced() for current table.
        """
        return self.driver.select_advanced(
            self.table_name,
            filters=filters,
            joins=joins,
            group_by=group_by,
            order_by=order_by,
            limit=limit,
            offset=offset,
            use_explain=use_explain
        )

    def select_aggregation(self, filters: dict = None, group_by: list = None,
                          aggregates: dict = None, order_by: list = None,
                          limit: int = None, use_explain: bool = False) -> Any:
        """SELECT with aggregation (COUNT, AVG, SUM, MIN, MAX).
        
        Proxy to driver.select_aggregation() for current table.
        Example aggregates: {"total": ("amount", "sum"), "avg_score": ("score", "avg")}
        """
        return self.driver.select_aggregation(
            self.table_name,
            filters=filters,
            group_by=group_by,
            aggregates=aggregates,
            order_by=order_by,
            limit=limit,
            use_explain=use_explain
        )


class DatabaseFacade:
    """Provides a proxy over different database driver implementations.
    Allows user to call db.users.insert(user).
    """

    def __init__(self, driver: Any):
        self.driver = driver

    def __getattr__(self, name: str) -> Any:
        return CollectionFacade(name, self.driver)
