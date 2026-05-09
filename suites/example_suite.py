import random
from typing import List
from datetime import datetime, timedelta

from faker import Faker

from framework.core.decorators import Setup, Suite, Benchmark
from data.schema import User, Order, Address, Product


@Setup
def global_setup(db) -> None:
    db.orders.create_index("status")

    fake = Faker()
    Faker.seed(42)
    random.seed(42)

    NUM_USERS = 500
    ORDERS_PER_USER = (0, 5)

    users: List[User] = []
    orders: List[Order] = []

    order_id_counter = 1

    for user_id in range(1, NUM_USERS + 1):
        address = Address(
            street=fake.street_address(),
            city=fake.city(),
            postal_code=fake.postcode(),
            country=fake.country()
        )

        created_at = fake.date_time_between(start_date="-2y", end_date="now")
        last_login = fake.date_time_between(start_date=created_at, end_date="now")

        user = User(
            id=user_id,
            username=fake.user_name(),
            email=fake.unique.email(),
            is_active=fake.boolean(chance_of_getting_true=90),
            created_at=created_at,
            last_login=last_login,
            address=address
        )
        users.append(user)

        num_orders = random.randint(*ORDERS_PER_USER)
        for _ in range(num_orders):
            num_products = random.randint(1, 4)
            items = []
            total_amount = 0.0

            for _ in range(num_products):
                price = round(random.uniform(10.0, 500.0), 2)
                total_amount += price
                items.append(Product(
                    product_id=random.randint(1000, 9999),
                    name=fake.ecommerce_name() if hasattr(fake, 'ecommerce_name') else fake.word(),
                    category=fake.word(),
                    price=price,
                    tags=[fake.word(), fake.word()]
                ))

            order = Order(
                id=order_id_counter,
                user_id=user_id,
                status=random.choice(["PENDING", "SHIPPED", "DELIVERED", "CANCELLED"]),
                total_amount=round(total_amount, 2),
                ordered_at=fake.date_time_between(start_date=created_at, end_date="now"),
                items=items
            )
            orders.append(order)
            order_id_counter += 1

    db.users.insert_many(users)
    db.orders.insert_many(orders)


@Suite("complex_ecommerce_suite")
class ComplexEcommerceSuite:

    @Benchmark("find_active_users")
    def find_active_users(self, db):
        return db.users.count({"is_active": True})

    @Benchmark("find_delivered_orders")
    def find_delivered_orders(self, db):
        return db.orders.count({"status": "DELIVERED"})

    @Benchmark("insert_single_order")
    def insert_single_order(self, db):
        order = Order(
            id=999999,
            user_id=1,
            status="PENDING",
            total_amount=99.99,
            ordered_at=datetime.now(),
            items=[
                Product(product_id=1111, name="Test Product", category="Test", price=99.99, tags=["benchmark"])
            ]
        )
        db.orders.insert(order)
        db.orders.delete({"id": 999999})

    @Benchmark("count_all_users")
    def count_all_users(self, db):
        return db.users.count()

    @Benchmark("count_all_orders")
    def count_all_orders(self, db):
        return db.orders.count()

    @Benchmark("find_inactive_users")
    def find_inactive_users(self, db):
        return db.users.count({"is_active": False})

    @Benchmark("find_pending_orders")
    def find_pending_orders(self, db):
        return db.orders.count({"status": "PENDING"})

    @Benchmark("find_high_value_orders")
    def find_high_value_orders(self, db):
        all_orders = db.orders.find_all()
        return len([o for o in all_orders if isinstance(o, dict) and o.get('total_amount', 0) > 500])

    @Benchmark("select_first_user")
    def select_first_user(self, db):
        result = db.users.select({"id": 1}, use_explain=True, explain_context="select_first_user")
        return len(result) if result else 0

    @Benchmark("update_user_status")
    def update_user_status(self, db):
        db.users.update({"id": 2}, {"is_active": False})
        db.users.update({"id": 2}, {"is_active": True})

    @Benchmark("update_order_status")
    def update_order_status(self, db):
        db.orders.update({"id": 1}, {"status": "SHIPPED"})
        db.orders.update({"id": 1}, {"status": "PENDING"})

    @Benchmark("delete_and_reinsert_order")
    def delete_and_reinsert_order(self, db):
        test_order = Order(
            id=888888,
            user_id=1,
            status="PENDING",
            total_amount=150.0,
            ordered_at=datetime.now(),
            items=[
                Product(product_id=2222, name="Test Item", category="Electronics", price=150.0, tags=["test"])
            ]
        )
        db.orders.insert(test_order)
        db.orders.delete({"id": 888888})

    @Benchmark("batch_insert_orders")
    def batch_insert_orders(self, db):
        batch_orders = []
        batch_size = 10
        for i in range(batch_size):
            order = Order(
                id=777777 + i,
                user_id=1,
                status="PENDING",
                total_amount=100.0 + i * 10,
                ordered_at=datetime.now(),
                items=[
                    Product(product_id=3000 + i, name=f"Batch Item {i}", category="Bulk", price=100.0 + i * 10, tags=["batch"])
                ]
            )
            batch_orders.append(order)
        db.orders.insert_many(batch_orders)
        for i in range(batch_size):
            db.orders.delete({"id": 777777 + i})

    @Benchmark("find_user_orders")
    def find_user_orders(self, db):
        return db.orders.count({"user_id": 1})

    @Benchmark("find_cancelled_orders")
    def find_cancelled_orders(self, db):
        return db.orders.count({"status": "CANCELLED"})

    @Benchmark("scan_all_users")
    def scan_all_users(self, db):
        result = db.users.find_all()
        return len(result) if result else 0

    @Benchmark("scan_all_orders")
    def scan_all_orders(self, db):
        result = db.orders.find_all()
        return len(result) if result else 0
