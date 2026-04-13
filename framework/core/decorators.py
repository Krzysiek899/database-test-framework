"""Declarative decorators for table/setup/suite/test registration."""

from __future__ import annotations

import functools
from typing import Callable, Optional, Type

from framework.core.registry import clear_registry, get_registry


def Table(name: Optional[str] = None):
    """Register a Pydantic model class as a framework table schema."""

    def decorator(model_cls: Type) -> Type:
        get_registry().register_table(model=model_cls, name=name)
        setattr(model_cls, "__framework_table_name__", name or model_cls.__name__.lower())
        return model_cls

    return decorator


def Setup(func: Optional[Callable] = None):
    """Register a single global setup function."""

    def decorator(fn: Callable) -> Callable:
        get_registry().register_setup(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return wrapper

    if func is None:
        return decorator
    return decorator(func)


def Benchmark(name: str):
    """Register a benchmark function with a given name."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("@Benchmark requires a non-empty benchmark name")

    def decorator(fn: Callable) -> Callable:
        setattr(fn, "__framework_benchmark_name__", name)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def Suite(name: Optional[str] = None):
    """Register a test suite class and discover methods marked with @Benchmark."""

    def decorator(suite_cls: Type) -> Type:
        get_registry().register_suite(suite_cls=suite_cls, name=name)
        setattr(suite_cls, "__framework_suite_name__", name or suite_cls.__name__)
        return suite_cls

    return decorator


get_registered_benchmarks = get_registry
