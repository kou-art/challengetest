#変更
from __future__ import annotations

from dataclasses import dataclass, field

from clang import cindex

from dataflow_analyzer import DataflowAnalyzer, DataflowRecord, RelatedSymbol

@dataclass
class RelatedVariableAnalysis:
    name: str
    usr: str
    kind: str
    source_expression: str
    dataflow: list[DataflowRecord] = field(default_factory=list)
    functions: set[str] = field(default_factory=set)


class RelatedVariableAnalyzer:
    VARIABLE_KINDS = {
        "VAR_DECL",
        "FIELD_DECL",
        "PARM_DECL"
    }

    def __init__(self,translation_units: list[cindex.TranslationUnit]) -> None:
        self.dataflow_analyzer = DataflowAnalyzer(translation_units)

    def analyze(
        self,
        dataflow: list[DataflowRecord],
        root_usr: str
    ) -> list[RelatedVariableAnalysis]:
        result = []
        queue: list[tuple[RelatedSymbol, str]] = []
        queued: set[str] = {root_usr}
        visited: set[str] = {root_usr}

        self._enqueue_related_variables(dataflow, queue, queued)

        while queue:
            symbol, source_expression = queue.pop(0)

            if ((not symbol.usr)or(symbol.usr in visited)):
                continue

            visited.add(symbol.usr)

            related_dataflow = self.dataflow_analyzer.analyze(
                target_name=symbol.name,
                target_usr=symbol.usr
            )

            functions = {
                flow.function
                for flow in related_dataflow
                if flow.function
            }

            result.append(
                RelatedVariableAnalysis(
                    name=symbol.name,
                    usr=symbol.usr,
                    kind=symbol.kind,
                    source_expression=source_expression,
                    dataflow=related_dataflow,
                    functions=functions
                )
            )

            self._enqueue_related_variables(
                related_dataflow,
                queue,
                queued
            )

        return result

    def _enqueue_related_variables(
        self,
        dataflow: list[DataflowRecord],
        queue: list[tuple[RelatedSymbol, str]],
        queued: set[str]
    ) -> None:
        for flow in dataflow:
            for symbol in flow.related_symbols:
                self._enqueue_symbol(
                    symbol,
                    flow.expression,
                    queue,
                    queued
                )

            if (flow.destination_symbol is not None):
                self._enqueue_symbol(
                    flow.destination_symbol,
                    flow.expression,
                    queue,
                    queued
                )

    def _enqueue_symbol(
        self,
        symbol: RelatedSymbol,
        source_expression: str,
        queue: list[tuple[RelatedSymbol, str]],
        queued: set[str]
    ) -> None:
        if (symbol.kind not in self.VARIABLE_KINDS):
            return

        if (not symbol.usr):
            return

        if (symbol.usr in queued):
            return

        queued.add(symbol.usr)
        queue.append((symbol, source_expression))