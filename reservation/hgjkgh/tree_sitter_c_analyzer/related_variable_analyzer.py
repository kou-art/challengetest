from __future__ import annotations

from dataclasses import dataclass, field

from analysis_models import DataflowRecord, RelatedSymbol
from dataflow_analyzer import DataflowAnalyzer
from symbol_index import SymbolDefinition, SymbolIndex
from ts_utils import walk


@dataclass
class RelatedVariableAnalysis:
    name: str
    symbol_id: str
    kind: str
    reasons: set[str] = field(default_factory=set)
    dataflow: list[DataflowRecord] = field(default_factory=list)
    functions: set[str] = field(default_factory=set)


class RelatedVariableAnalyzer:
    def __init__(self, dataflow_analyzer: DataflowAnalyzer, symbol_index: SymbolIndex) -> None:
        self.dataflow_analyzer = dataflow_analyzer
        self.symbol_index = symbol_index
        self.parsed_files = dataflow_analyzer.parsed_files

    def analyze(self, dataflow: list[DataflowRecord], root_symbol_id: str) -> list[RelatedVariableAnalysis]:
        seeds: dict[str, tuple[SymbolDefinition, set[str]]] = {}

        self._add_variables_from_target_usages(dataflow, root_symbol_id, seeds)
        self._add_globals_from_target_functions(dataflow, root_symbol_id, seeds)

        result: list[RelatedVariableAnalysis] = []

        for symbol_id in sorted(seeds):
            definition, reasons = seeds[symbol_id]
            variable_dataflow = self.dataflow_analyzer.analyze(definition)
            functions = {flow.function for flow in variable_dataflow if flow.function}

            result.append(
                RelatedVariableAnalysis(
                    name=definition.name,
                    symbol_id=definition.symbol_id,
                    kind=definition.kind,
                    reasons=reasons,
                    dataflow=variable_dataflow,
                    functions=functions
                )
            )

        return result

    def _add_variables_from_target_usages(
        self,
        dataflow: list[DataflowRecord],
        root_symbol_id: str,
        seeds: dict[str, tuple[SymbolDefinition, set[str]]]
    ) -> None:
        for flow in dataflow:
            for symbol in flow.related_symbols:
                self._add_seed(symbol, root_symbol_id, '対象変数の使用箇所に使われる変数', seeds)

            if flow.destination_symbol is not None:
                self._add_seed(flow.destination_symbol, root_symbol_id, '対象変数の値が代入される変数', seeds)

    def _add_globals_from_target_functions(
        self,
        dataflow: list[DataflowRecord],
        root_symbol_id: str,
        seeds: dict[str, tuple[SymbolDefinition, set[str]]]
    ) -> None:
        function_locations = {(flow.file, flow.function) for flow in dataflow if flow.function}

        for file_name, function_name in function_locations:
            parsed_file = self.symbol_index.parsed_file_for(file_name)
            if parsed_file is None or function_name is None:
                continue

            function_node = self.symbol_index.find_function_node(parsed_file, function_name)
            if function_node is None:
                continue
            body = function_node.child_by_field_name('body')
            if body is None:
                continue

            for node in walk(body):
                if node.type not in {'identifier', 'field_identifier'}:
                    continue
                if self.symbol_index.is_declaration_node(parsed_file, node):
                    continue

                definitions = self.symbol_index.resolve_reference_candidates(parsed_file, node)
                for definition in definitions:
                    if definition.kind != 'VAR_DECL':
                        continue
                    if definition.scope not in {'<global>', '<file>'}:
                        continue
                    if definition.symbol_id == root_symbol_id:
                        continue
                    if self.symbol_index.is_constant_definition(definition):
                        continue

                    self._merge_seed(definition, '対象変数を使用する関数内のグローバル変数', seeds)

    def _add_seed(
        self,
        symbol: RelatedSymbol,
        root_symbol_id: str,
        reason: str,
        seeds: dict[str, tuple[SymbolDefinition, set[str]]]
    ) -> None:
        if symbol.kind not in SymbolIndex.VARIABLE_KINDS:
            return
        if not symbol.symbol_id or symbol.symbol_id == root_symbol_id:
            return

        definition = self.symbol_index.best_definition(symbol.symbol_id)
        if definition is None:
            return
        if self.symbol_index.is_constant_definition(definition):
            return

        self._merge_seed(definition, reason, seeds)

    @staticmethod
    def _merge_seed(
        definition: SymbolDefinition,
        reason: str,
        seeds: dict[str, tuple[SymbolDefinition, set[str]]]
    ) -> None:
        if definition.symbol_id in seeds:
            seeds[definition.symbol_id][1].add(reason)
            return

        seeds[definition.symbol_id] = (definition, {reason})
