from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RelatedSymbol:
    name: str
    symbol_id: str | None
    kind: str
    file: str | None
    line: int | None


@dataclass
class DataflowRecord:
    direction: str
    operation: str
    function: str | None
    file: str
    line: int
    expression: str
    operator: str | None = None
    value_expression: str | None = None
    condition_expression: str | None = None
    related_symbols: list[RelatedSymbol] = field(default_factory=list)
    effects: list[RelatedSymbol] = field(default_factory=list)
    callee: str | None = None
    argument_index: int | None = None
    destination_symbol: RelatedSymbol | None = None
