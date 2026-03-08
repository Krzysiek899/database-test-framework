"""
@benchmark decorator – Benchmarking DSL.

Usage::

    @benchmark("Select all users")
    def test_select_all(driver):
        return driver.execute("SELECT * FROM users;")

The decorator registers the function in a global test registry.
At runtime the BenchmarkRunner iterates the registry, injects the
appropriate driver, and wraps each call with telemetry.
"""

from __future__ import annotations

import functools
from typing import Callable, Dict, List, Optional

# Global registry: list of (name, function, options)
_BENCHMARK_REGISTRY: List[Dict] = []


def benchmark(
    name: Optional[str] = None,
    warmup: Optional[int] = None,
    iterations: Optional[int] = None,
):
    """Decorator that registers a function as a benchmark test.

    Parameters
    ----------
    name:
        Human-readable name. Defaults to the function's ``__name__``.
    warmup:
        Override global warmup iterations for this test.
    iterations:
        Override global benchmark iterations for this test.
    """

    def decorator(func: Callable) -> Callable:
        entry = {
            "name": name or func.__name__,
            "func": func,
            "warmup": warmup,
            "iterations": iterations,
        }
        _BENCHMARK_REGISTRY.append(entry)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_registered_benchmarks() -> List[Dict]:
    """Return a copy of the global benchmark registry."""
    return list(_BENCHMARK_REGISTRY)


def clear_registry() -> None:
    """Remove all registered benchmarks (useful for tests)."""
    _BENCHMARK_REGISTRY.clear()

