from __future__ import annotations

from dataclasses import dataclass, field

from analysis_models import DataflowRecord
from dataflow_analyzer import DataflowAnalyzer
from related_variable_analyzer import RelatedVariableAnalysis, RelatedVariableAnalyzer
from symbol_index import SymbolDefinition, SymbolIndex


@dataclass
class VariableCandidate:
    name: str
    symbol_id: str
    kind: str
    declarations: list[SymbolDefinition] = field(default_factory=list)
    functions: set[str] = field(default_factory=set)
    dataflow: list[DataflowRecord] = field(default_factory=list)
    related_variables: list[RelatedVariableAnalysis] = field(default_factory=list)
    related_definitions: object | None = None


class VariableAnalyzer:
    def __init__(self, symbol_index: SymbolIndex, dataflow_analyzer: DataflowAnalyzer) -> None:
        self.symbol_index = symbol_index
        self.dataflow_analyzer = dataflow_analyzer
        self.related_variable_analyzer = RelatedVariableAnalyzer(dataflow_analyzer, symbol_index)

    def analyze(self, target_name: str) -> list[VariableCandidate]:
        grouped: dict[str, list[SymbolDefinition]] = {}
        for definition in self.symbol_index.find_variables(target_name):
            grouped.setdefault(definition.symbol_id, []).append(definition)

        candidates: list[VariableCandidate] = []

        for symbol_id, definitions in grouped.items():
            target = self._best_definition(definitions)
            if target is None:
                continue

            dataflow = self.dataflow_analyzer.analyze(target)
            functions = {flow.function for flow in dataflow if flow.function}
            related_variables = self.related_variable_analyzer.analyze(dataflow, target.symbol_id)

            candidates.append(
                VariableCandidate(
                    name=target.name,
                    symbol_id=target.symbol_id,
                    kind=target.kind,
                    declarations=definitions,
                    functions=functions,
                    dataflow=dataflow,
                    related_variables=related_variables
                )
            )

        return candidates

    @staticmethod
    def _best_definition(definitions: list[SymbolDefinition]) -> SymbolDefinition | None:
        defined = [definition for definition in definitions if definition.is_definition]
        if defined:
            return defined[0]
        return definitions[0] if definitions else None
