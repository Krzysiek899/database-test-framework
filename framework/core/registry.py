from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Type


@dataclass
class TableMeta:
    name: str
    model: Type


@dataclass
class BenchmarkMeta:
    name: str
    fn_name: str
    fn: Callable


@dataclass
class SuiteMeta:
    name: str
    suite_cls: Type
    benchmarks: List[BenchmarkMeta] = field(default_factory=list)


@dataclass
class SetupMeta:
    fn: Callable


class FrameworkRegistry:
    def __init__(self) -> None:
        self.tables: List[TableMeta] = []
        self.suites: List[SuiteMeta] = []
        self.setup: Optional[SetupMeta] = None

    def register_table(self, model: Type, name: Optional[str] = None) -> TableMeta:
        table_name = name or model.__name__.lower()
        if any(t.name == table_name for t in self.tables):
            raise ValueError(f"Table '{table_name}' is already registered")
        meta = TableMeta(name=table_name, model=model)
        self.tables.append(meta)
        return meta

    def register_setup(self, fn: Callable) -> SetupMeta:
        if self.setup is not None:
            raise ValueError("Global @Setup already registered")
        meta = SetupMeta(fn=fn)
        self.setup = meta
        return meta

    def register_suite(self, suite_cls: Type, name: Optional[str] = None) -> SuiteMeta:
        suite_name = name or suite_cls.__name__
        benchmarks: List[BenchmarkMeta] = []
        for attr in suite_cls.__dict__.values():
            benchmark_name = getattr(attr, "__framework_benchmark_name__", None)
            if benchmark_name:
                benchmarks.append(BenchmarkMeta(name=benchmark_name, fn_name=attr.__name__, fn=attr))
        if not benchmarks:
            raise ValueError(f"Suite '{suite_name}' has no methods decorated with @Benchmark")
        meta = SuiteMeta(name=suite_name, suite_cls=suite_cls, benchmarks=benchmarks)
        self.suites.append(meta)
        return meta

    def clear(self) -> None:
        self.tables.clear()
        self.suites.clear()
        self.setup = None


_registry = FrameworkRegistry()


def get_registry() -> FrameworkRegistry:
    return _registry


def clear_registry() -> None:
    _registry.clear()
