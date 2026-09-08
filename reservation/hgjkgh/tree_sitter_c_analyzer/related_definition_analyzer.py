from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from analysis_models import RelatedSymbol
from parsed_file import ParsedFile
from symbol_index import SymbolDefinition, SymbolIndex
from ts_utils import walk


@dataclass
class RelatedDefinitionResult:
    definitions: list[SymbolDefinition] = field(default_factory=list)
    headers: set[str] = field(default_factory=set)
    source_files: set[str] = field(default_factory=set)
    scores: dict[tuple, int] = field(default_factory=dict)
    reasons: dict[tuple, str] = field(default_factory=dict)


class RelatedDefinitionAnalyzer:
    def __init__(self, symbol_index: SymbolIndex, parsed_files: list[ParsedFile]) -> None:
        self.symbol_index = symbol_index
        self.parsed_files = parsed_files

    def analyze(self, candidate) -> RelatedDefinitionResult:
        result = RelatedDefinitionResult()
        seen: set[tuple] = set()

        # 1. 対象変数の定義・宣言は両方残す
        for definition in self.symbol_index.find_by_id(candidate.symbol_id):
            self._add_definition(definition, result, seen, 100, '対象変数の定義・宣言', follow_types=True)

        # 2, 3. 対象変数の使用箇所を含む関数は定義だけ取得
        target_functions = self._target_function_locations(candidate.dataflow)
        for file_name, function_name in target_functions:
            definition = self.symbol_index.find_function_definition(function_name, file_name)
            if definition is not None:
                self._add_definition(definition, result, seen, 95, '対象変数の使用箇所を含む関数')

        # 4. 上記関数内のグローバル変数と関数
        for file_name, function_name in target_functions:
            self._add_globals_and_functions_in_function(
                file_name,
                function_name,
                candidate.symbol_id,
                result,
                seen
            )

        # 5, 6. 対象変数の使用箇所に直接使われる定数・関数
        for flow in candidate.dataflow:
            for symbol in flow.related_symbols:
                self._add_target_usage_symbol(symbol, result, seen)

            if flow.callee:
                definition = self.symbol_index.find_function_definition(flow.callee, flow.file)
                if definition is None:
                    definition = self.symbol_index.find_function_definition(flow.callee)
                if definition is not None:
                    self._add_definition(definition, result, seen, 92, '対象変数の使用箇所に使われる関数')

        # 7. 関連変数は定義を入れ、その変数へ代入される値の定義を取得
        for variable in candidate.related_variables:
            for definition in self.symbol_index.find_by_id(variable.symbol_id):
                if definition.is_definition:
                    self._add_definition(definition, result, seen, 85, '追跡対象の関連変数', follow_types=True)

            self._add_assigned_value_definitions(variable.dataflow, result, seen)

        result.definitions.sort(
            key=lambda definition: (
                -result.scores.get(self._key(definition), 0),
                definition.file,
                definition.start_line,
                definition.kind,
                definition.name
            )
        )
        return result

    def _target_function_locations(self, flows) -> set[tuple[str, str]]:
        return {(flow.file, flow.function) for flow in flows if flow.function}

    def _add_globals_and_functions_in_function(
        self,
        file_name: str,
        function_name: str,
        target_symbol_id: str,
        result: RelatedDefinitionResult,
        seen: set[tuple]
    ) -> None:
        parsed_file = self.symbol_index.parsed_file_for(file_name)
        if parsed_file is None:
            return

        function_node = self.symbol_index.find_function_node(parsed_file, function_name)
        if function_node is None:
            return
        body = function_node.child_by_field_name('body')
        if body is None:
            return

        for node in walk(body):
            if node.type not in {'identifier', 'field_identifier'}:
                continue
            if self.symbol_index.is_declaration_node(parsed_file, node):
                continue

            definitions = self.symbol_index.resolve_reference_candidates(parsed_file, node)
            for definition in definitions:
                if definition.symbol_id == target_symbol_id:
                    continue

                if definition.kind == 'FUNCTION_DECL':
                    function_definition = self.symbol_index.find_function_definition(definition.name, definition.file)
                    if function_definition is None:
                        function_definition = self.symbol_index.find_function_definition(definition.name)
                    if function_definition is not None:
                        self._add_definition(
                            function_definition,
                            result,
                            seen,
                            88,
                            '対象変数を使用する関数内の関数'
                        )
                    continue

                if definition.kind == 'VAR_DECL' and definition.scope in {'<global>', '<file>'}:
                    preferred = self.symbol_index.best_definition(definition.symbol_id)
                    if preferred is not None:
                        self._add_definition(
                            preferred,
                            result,
                            seen,
                            86,
                            '対象変数を使用する関数内のグローバル変数',
                            follow_types=True
                        )

    def _add_target_usage_symbol(
        self,
        symbol: RelatedSymbol,
        result: RelatedDefinitionResult,
        seen: set[tuple]
    ) -> None:
        definition = self._resolve_related_symbol(symbol)
        if definition is None:
            return

        if self.symbol_index.is_constant_definition(definition):
            self._add_definition(definition, result, seen, 93, '対象変数の使用箇所に使われる定数')
            return

        if definition.kind == 'FUNCTION_DECL':
            function_definition = self.symbol_index.find_function_definition(definition.name, definition.file)
            if function_definition is None:
                function_definition = self.symbol_index.find_function_definition(definition.name)
            if function_definition is not None:
                self._add_definition(function_definition, result, seen, 92, '対象変数の使用箇所に使われる関数')

    def _add_assigned_value_definitions(self, flows, result: RelatedDefinitionResult, seen: set[tuple]) -> None:
        for flow in flows:
            if flow.direction not in {'into_target', 'target_self_update'}:
                continue
            if flow.operation not in {'initialization', 'assignment', 'compound_assignment'}:
                continue

            for symbol in flow.related_symbols:
                definition = self._resolve_related_symbol(symbol)
                if definition is None:
                    continue

                if definition.kind == 'FUNCTION_DECL':
                    function_definition = self.symbol_index.find_function_definition(definition.name, definition.file)
                    if function_definition is None:
                        function_definition = self.symbol_index.find_function_definition(definition.name)
                    if function_definition is not None:
                        self._add_definition(
                            function_definition,
                            result,
                            seen,
                            82,
                            '関連変数へ代入される値を作る関数'
                        )
                    continue

                preferred = self.symbol_index.best_definition(definition.symbol_id)
                if preferred is None:
                    continue

                reason = (
                    '関連変数へ代入される定数の定義'
                    if self.symbol_index.is_constant_definition(preferred)
                    else '関連変数へ代入される値の定義'
                )
                self._add_definition(preferred, result, seen, 80, reason, follow_types=True)

    def _resolve_related_symbol(self, symbol: RelatedSymbol) -> SymbolDefinition | None:
        if symbol.symbol_id:
            definition = self.symbol_index.best_definition(symbol.symbol_id)
            if definition is not None:
                return definition

        return self.symbol_index.find_unique_by_name(symbol.name)

    def _add_definition(
        self,
        definition: SymbolDefinition,
        result: RelatedDefinitionResult,
        seen: set[tuple],
        score: int,
        reason: str,
        follow_types: bool = False
    ) -> None:
        if definition.kind == 'FUNCTION_DECL' and not definition.is_definition:
            return

        key = self._key(definition)
        previous_score = result.scores.get(key, -1)
        if key not in seen:
            seen.add(key)
            result.definitions.append(definition)

            suffix = Path(definition.file).suffix.lower()
            if suffix == '.h':
                result.headers.add(definition.file)
            elif suffix == '.c':
                result.source_files.add(definition.file)

        if score > previous_score:
            result.scores[key] = score
            result.reasons[key] = reason

        if not follow_types:
            return

        self._add_direct_types(definition, result, seen)

    def _add_direct_types(
        self,
        definition: SymbolDefinition,
        result: RelatedDefinitionResult,
        seen: set[tuple]
    ) -> None:
        for type_name in definition.related_type_names:
            type_definitions = [
                item for item in self.symbol_index.find_by_name(type_name)
                if item.kind in SymbolIndex.TYPE_KINDS and item.is_definition
            ]
            for type_definition in type_definitions:
                self._add_definition(type_definition, result, seen, 70, '選択された変数に必要な型定義')

    @staticmethod
    def _key(definition: SymbolDefinition) -> tuple:
        return (
            definition.kind,
            definition.symbol_id,
            definition.file,
            definition.start_line,
            definition.end_line
        )
