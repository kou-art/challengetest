from __future__ import annotations

from pathlib import Path

from dataflow_analyzer import DataflowAnalyzer
from related_definition_analyzer import RelatedDefinitionAnalyzer
from scanner import ProjectScanner
from symbol_index import SymbolIndex
from tree_sitter_manager import TreeSitterManager
from tree_sitter_parser import TreeSitterProjectParser
from variable_analyzer import VariableAnalyzer


def main() -> None:
    root = Path(__file__).parent / 'tests'
    files = ProjectScanner().scan(root)
    parser = TreeSitterProjectParser(TreeSitterManager().create_parser())
    parse_result = parser.parse_files(files.all_files)

    symbol_index = SymbolIndex(parse_result.parsed_files, root)
    symbol_index.build()
    dataflow = DataflowAnalyzer(parse_result.parsed_files, symbol_index)
    candidates = VariableAnalyzer(symbol_index, dataflow).analyze('g_temperature')

    assert candidates, 'g_temperatureが見つかりません'
    candidate = candidates[0]
    candidate.related_definitions = RelatedDefinitionAnalyzer(symbol_index, parse_result.parsed_files).analyze(candidate)

    assert any(flow.operation == 'assignment' and 'g_temperature = a' in flow.expression for flow in candidate.dataflow)
    assert any(variable.name == 'a' for variable in candidate.related_variables)

    names = {definition.name for definition in candidate.related_definitions.definitions}
    assert 'g_temperature' in names
    assert 'update_temperature' in names
    assert 'get_temperature' in names
    assert 'a' in names
    assert 'source_value' in names
    assert 'adjust_value' in names
    assert 'TEMP_LIMIT' in names
    assert 'unrelated_global' not in names
    assert 'unrelated_function' not in names
    assert 'UNUSED_LIMIT' not in names

    print('Smoke test: OK')
    print(f'Target dataflow    : {len(candidate.dataflow)}')
    print(f'Related variables  : {[variable.name for variable in candidate.related_variables]}')
    print(f'Selected definitions: {sorted(names)}')


if __name__ == '__main__':
    main()
