# Database Test Framework

A lightweight, container-based database benchmarking orchestration framework.

## Project Structure

```text
database-test-framework/
├── config.yaml          # Defines engines (Docker), connection info
├── run_benchmarks.py    # Main entry point (CLI)
├── requirements.txt     # Python dependencies
├── data/
│   └── schema.py        # Framework models schema via @Table declarative API
├── framework/
│   ├── core/
│   │   ├── config.py    # YAML parser & validator
│   │   ├── decorators.py# Declarative decorators (@Table, @Setup, @Suite, @Benchmark)
│   │   ├── facade.py    # Unifed Database Access Proxy wrapper
│   │   ├── registry.py  # Global metadata registry for framework decorations
│   │   └── runner.py    # BenchmarkRunner – spins up Docker, connects, runs queries, flushes stats
│   ├── drivers/
│   │   ├── base.py      # Abstract DatabaseDriverInterface (connect, disconnect, execute)
│   │   ├── factory.py   # create_driver() factory method
│   │   ├── postgres.py  # PostgreSQL driver backed by SQLAlchemy
│   │   ├── mongodb.py   # Mongo driver
│   │   ├── mysql.py     # MySQL driver backed by SQLAlchemy
│   │   └── couchdb.py   # CouchDB driver
│   ├── infra/
│   │   └── provider.py  # Docker container lifecycle management
│   ├── reporting/
│   │   └── report.py    # matplotlib & JSON report generator
│   └── telemetry/
│       └── observer.py  # Container stats poller & execution timing
└── suites/
    └── example_suite.py # The test files written using your library
```

## Design Patterns

| Pattern           | Where                           | Purpose                                   |
|-------------------|---------------------------------|-------------------------------------------|
| **Factory**       | `drivers/factory.py`            | Instantiate correct driver from config     |
| **Strategy**      | `drivers/base.py`               | Unified interface for SQL & NoSQL          |
| **Context Manager** | `infra/provider.py`, `drivers/base.py` | Safe resource cleanup              |
| **Decorator**     | `core/decorators.py`            | `@benchmark` DSL for test registration     |
| **Observer**      | `telemetry/observer.py`         | Non-intrusive performance data capture     |

## Prerequisites

- **Python 3.10+**
- **Docker** (running daemon)

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure engines

Edit `config.yaml` to define which database engines to benchmark, schema definitions, and seeding parameters.

### 3. Write benchmark tests

Create a Python module in `suites/` using the `@benchmark` decorator:

```python
from framework.core.decorators import benchmark

@benchmark(name="select_all_users")
def select_all_users(driver):
    if driver.engine_name == "mongodb":
        return driver.execute(lambda db: list(db.users.find()))
    return driver.execute("SELECT * FROM users;")
```

### 4. Run benchmarks

```bash
# All engines, default suite
python run_benchmarks.py

# Specific engine
python run_benchmarks.py --engines postgres

# Custom config & suite
python run_benchmarks.py --config my_config.yaml --suite suites.my_suite

# Verbose logging
python run_benchmarks.py --log-level DEBUG
```

### 5. Review results

Results are saved in the `results/` directory:
- `<engine>_<timestamp>.json` – full timing + resource data
- `<engine>_<timestamp>_timings.csv` – flat timing CSV
- `comparative_report.json` – side-by-side summary
- `benchmark_comparison.png` – bar chart visualization

## Execution Workflow

1. **Config**: Read `config.yaml` and identify target engines.
2. **Setup**: Spin up Docker containers; poll health-checks until ready.
3. **Init**: Apply schema/index definitions; bulk-load deterministic data.
4. **Warm-up**: Run non-measured queries to populate DB caches/buffers.
5. **Benchmark**: Iteratively call `@benchmark` functions while capturing timing + Docker stats.
6. **Teardown**: Close connections; stop & remove containers.
7. **Report**: Generate comparative JSON, CSV, and PNG chart.

## Configuration Reference

See `config.yaml` for a fully commented example covering:
- `global` – seed, iteration counts, results directory
- `engines` – Docker image, ports, env vars, health-checks, resource limits
- `schema` – engine-agnostic table/collection definitions with indexes
- `seeding` – row counts per table

## Extending

### Adding a new engine driver

1. Create `framework/drivers/myengine.py` implementing `DatabaseDriverInterface`.
2. Register it in `framework/drivers/factory.py`:
   ```python
   _REGISTRY["myengine"] = MyEngineDriver
   ```
3. Add the engine section to `config.yaml`.
4. Add schema translation logic to `DataOrchestrator` if needed.
