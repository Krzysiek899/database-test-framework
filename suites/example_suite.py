"""
Example benchmark suite.

Each function decorated with ``@benchmark(...)`` is automatically registered
and will be executed against every configured engine.

The function receives a single argument – the database driver instance.
  • For SQL engines: use ``driver.execute("SELECT ...")``
  • For NoSQL engines: use ``driver.execute(lambda db: db.collection.find(...))``

To handle both SQL and NoSQL in a single function, inspect ``driver.engine_name``
or write separate functions.
"""

from framework.core.decorators import benchmark


# ---- Read-heavy queries ---------------------------------------------------

@benchmark(name="select_all_users")
def select_all_users(driver):
    """Full table scan on users."""
    if driver.engine_name == "mongodb":
        return driver.execute(lambda db: list(db.users.find()))
    return driver.execute("SELECT * FROM users;")


@benchmark(name="select_user_by_username")
def select_user_by_username(driver):
    """Point lookup on indexed column."""
    if driver.engine_name == "mongodb":
        return driver.execute(lambda db: db.users.find_one({"username": "user_500"}))
    return driver.execute(
        "SELECT * FROM users WHERE username = %s;", ("user_500",)
    )


@benchmark(name="count_orders")
def count_orders(driver):
    """Simple aggregation."""
    if driver.engine_name == "mongodb":
        return driver.execute(lambda db: db.orders.count_documents({}))
    return driver.execute("SELECT count(*) FROM orders;")


# ---- Aggregation ----------------------------------------------------------

@benchmark(name="orders_total_by_user")
def orders_total_by_user(driver):
    """GROUP BY aggregation with SUM."""
    if driver.engine_name == "mongodb":
        return driver.execute(
            lambda db: list(
                db.orders.aggregate(
                    [
                        {
                            "$group": {
                                "_id": "$user_id",
                                "total": {"$sum": "$price"},
                                "count": {"$sum": 1},
                            }
                        },
                        {"$sort": {"total": -1}},
                        {"$limit": 10},
                    ]
                )
            )
        )
    return driver.execute(
        "SELECT user_id, SUM(price) AS total, COUNT(*) AS cnt "
        "FROM orders GROUP BY user_id ORDER BY total DESC LIMIT 10;"
    )


# ---- Join / Lookup --------------------------------------------------------

@benchmark(name="orders_with_user_info")
def orders_with_user_info(driver):
    """Join orders with users (SQL) / $lookup (Mongo)."""
    if driver.engine_name == "mongodb":
        return driver.execute(
            lambda db: list(
                db.orders.aggregate(
                    [
                        {
                            "$lookup": {
                                "from": "users",
                                "localField": "user_id",
                                "foreignField": "id",
                                "as": "user",
                            }
                        },
                        {"$limit": 50},
                    ]
                )
            )
        )
    return driver.execute(
        "SELECT o.*, u.username, u.email "
        "FROM orders o JOIN users u ON o.user_id = u.id "
        "LIMIT 50;"
    )


# ---- Range scan -----------------------------------------------------------

@benchmark(name="recent_orders")
def recent_orders(driver):
    """Range query on indexed timestamp column."""
    if driver.engine_name == "mongodb":
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        return driver.execute(
            lambda db: list(
                db.orders.find({"ordered_at": {"$gte": cutoff}}).limit(100)
            )
        )
    return driver.execute(
        "SELECT * FROM orders "
        "WHERE ordered_at >= NOW() - INTERVAL '30 days' "
        "LIMIT 100;"
    )

