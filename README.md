# Database Test Framework

A lightweight, container-based database benchmarking framework supporting multiple relational and document database engines.

## Overview
This framework allows developers to easily benchmark different database engines (PostgreSQL, MongoDB, MySQL, CouchDB) using a unified, declarative Python API based on Pydantic models and decorators. Test suites are engine-agnostic – you write your logic once, and the framework automatically spins up Docker containers, initializes schemas, seeds data, runs your measurements, and generates comparative reports.

## Prerequisites
- **Python 3.10+**
- **Docker** (running daemon)

---

## 1. Installation

```bash
git clone <repository_url>
cd database-test-framework
pip install -r requirements.txt
```

## 2. Configuration (`config.yaml`)

Edit the `config.yaml` to define global test variables and adjust your targeted database Docker engines. 

```yaml
# Global settings applied to every benchmark run
global:
  warmup_iterations: 3        # Number of queries executed before metrics capture
  benchmark_iterations: 10    # Measured iterations per test function
  results_dir: "results"      # Output directory for telemetry JSON / CSV reports
  stats_interval_sec: 0.5     # Container stats polling interval (in seconds)

# Engine definitions (Docker image, ports, limits)
engines:
  postgres:
    engine_type: postgres
    image: "postgres:16-alpine"
    port: 5432
    host_port: 5432
    environment:
      POSTGRES_USER: bench
      POSTGRES_PASSWORD: bench
      POSTGRES_DB: benchdb
  
  mongodb:
    engine_type: mongodb
    image: "mongo:7"
    port: 27017
    host_port: 27017
```
*(The framework currently offers built-in support for `postgres`, `mysql`, `mongodb`, and `couchdb` engine types).*

---

## 3. Defining Data Models

Navigate to the `data/schema.py` file to declare the exact structure of tables or documents for your tests. Models are strictly defined via Pydantic classes and decorated with `@Table("<name>")`. Models can be nested (Lists, dicts) for document databases seamlessly, and are selectively adjusted for SQL models logic.

```python
from typing import List
from pydantic import BaseModel
from framework.core.decorators import Table

class Product(BaseModel):
    product_id: int
    name: str
    price: float

@Table("orders")
class Order(BaseModel):
    id: int
    user_id: int
    status: str
    items: List[Product]
```

---

## 4. Writing Benchmarks (`suites/`)

Use declarative decorators to build a benchmark pipeline. Each file in `suites/` that imports the suite will define the logic for:
1. **`@Setup`**: Database initialization function used to generate your mock data (e.g. using `Faker`), executed once before the entire suite runs.
2. **`@Suite` & `@Benchmark`**: Defined tests meant for measuring response times.

Every test has access to the database proxy object `db`, providing a unified interface (`db.<table_name>.<operation>`).

```python
from datetime import datetime
from framework.core.decorators import Setup, Suite, Benchmark
from data.schema import Order

@Setup
def init_database(db) -> None:
    # Generate mock data for the test
    my_order = Order(id=1, user_id=10, status="SHIPPED", items=[])
    db.orders.insert(my_order)
    # You can also use insert_many(List[...])
    
@Suite("my_ecommerce_suite")
class EcommerceSuite:
    
    @Benchmark("find_shipped_orders")
    def find_shipped_orders(self, db):
        # Unified API for SQL and NoSQL queries in the framework
        return db.orders.count({"status": "SHIPPED"})
        
    @Benchmark("select_all_orders")
    def select_all_orders(self, db):
        return db.orders.find_all()
```
**Supported operations on `db.table_name`:**
`insert(entity)`, `insert_many(entities)`, `update(filter, data)`, `update_many(filter, data)`, `delete(filter)`, `delete_many(filter)`, `select(filter)`, `find_all()`, `count(filter)`.

---

## 5. Running Tests

Run the framework locally from the source base:

```bash
# Run benchmarks on ALL enabled engines in config.yaml
python run_benchmarks.py

# Limit testing to specific engine
python run_benchmarks.py --engines postgres

# Point to specific suite execution module
python run_benchmarks.py --suite suites.my_suite
```

---

## 6. Reviewing Results

After the execution concludes, the framework guarantees full cleanup of the Docker containers, and saves the artifacts directly under `results/`:
- **`comparative_report.json`** – Comparative summary for each test on every engine tested.
- **`benchmark_comparison.png`** – Automatic bar chart visualization of execution speeds across tested query definitions.
- **`<engine>_timings.csv`** – Time metrics & container stat outputs detailing CPU/Memory impacts.
