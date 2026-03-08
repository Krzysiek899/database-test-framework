# Database Benchmarking Framework

A modular, reproducible, engine-agnostic framework for comparing SQL and NoSQL database performance. It manages the full lifecycle: environment provisioning via Docker, schema/data initialization, query execution, and telemetry gathering.

## Architecture

```
framework/
├── core/                # Runner, decorators, config loader
│   ├── config.py        # YAML config reader & validator
│   ├── decorators.py    # @benchmark decorator (DSL)
│   └── runner.py        # BenchmarkRunner – main orchestrator
├── infra/               # Infrastructure layer
│   └── provider.py      # InfraProvider – Docker container lifecycle
├── drivers/             # Abstraction layer
│   ├── base.py          # DatabaseDriverInterface (Strategy pattern)
│   ├── factory.py       # DriverFactory (Factory pattern)
│   ├── postgres.py      # PostgreSQL driver (psycopg2)
│   └── mongo.py         # MongoDB driver (pymongo)
├── data/                # Schema & Data layer
│   └── orchestrator.py  # DataOrchestrator – schema, seeding, warm-up
├── telemetry/           # Telemetry module
│   └── observer.py      # Observer – timing + Docker stats
└── reporting/           # Report generation
    └── report.py        # Comparative JSON, CSV & chart output
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

