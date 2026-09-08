from __future__ import annotations

from pathlib import Path

from code_extractor import CodeExtractor
from context_builder import ContextBuilder
from dataflow_analyzer import DataflowAnalyzer
from related_definition_analyzer import RelatedDefinitionAnalyzer
from relevance_analyzer import RelevanceAnalyzer
from scanner import ProjectScanner
from symbol_index import SymbolIndex
from tree_sitter_manager import TreeSitterManager
from tree_sitter_parser import TreeSitterProjectParser
from variable_analyzer import VariableAnalyzer


def main() -> None:
    project_root = Path(input('Cプロジェクトのルートフォルダ: ').strip()).resolve()
    target_variable = input('調べたい変数名: ').strip()

    project_files = ProjectScanner().scan(project_root)
    print(f'Root : {project_files.root}')
    print(f'.c   : {len(project_files.c_files)}')
    print(f'.h   : {len(project_files.h_files)}')

    manager = TreeSitterManager()
    parser = TreeSitterProjectParser(manager.create_parser())
    parse_result = parser.parse_files(project_files.all_files)

    print(f'Parse OK     : {len(parse_result.parsed_files)}')
    print(f'Parse failed : {len(parse_result.failed_files)}')

    error_files = [parsed_file for parsed_file in parse_result.parsed_files if parsed_file.error_count]
    print(f'ERROR nodes  : {sum(parsed_file.error_count for parsed_file in error_files)}')
    for parsed_file in error_files[:10]:
        print(f'  {parsed_file.path}: {parsed_file.error_count}')

    for path, message in parse_result.failed_files:
        print(f'FAILED: {path}: {message}')

    if not parse_result.parsed_files:
        print('解析可能なファイルがありません。')
        return

    symbol_index = SymbolIndex(parse_result.parsed_files, project_files.root)
    symbol_index.build()

    dataflow_analyzer = DataflowAnalyzer(parse_result.parsed_files, symbol_index)
    variable_analyzer = VariableAnalyzer(symbol_index, dataflow_analyzer)
    candidates = variable_analyzer.analyze(target_variable)

    if not candidates:
        print(f'対象変数が見つかりません: {target_variable}')
        return

    related_analyzer = RelatedDefinitionAnalyzer(symbol_index, parse_result.parsed_files)
    relevance_analyzer = RelevanceAnalyzer()
    code_extractor = CodeExtractor(parse_result.parsed_files)
    context_builder = ContextBuilder(max_tokens=90000)

    for number, candidate in enumerate(candidates, 1):
        candidate.related_definitions = related_analyzer.analyze(candidate)
        ranked = relevance_analyzer.rank(candidate)
        blocks = code_extractor.extract(ranked)

        if len(candidates) == 1:
            output = project_root / 'llm_context.txt'
        else:
            output = project_root / f'llm_context_{number}_{candidate.name}.txt'

        context_builder.save(output, candidate, blocks)

        print()
        print(f'Candidate {number}: {candidate.name}')
        print(f'  ID               : {candidate.symbol_id}')
        print(f'  kind             : {candidate.kind}')
        print(f'  direct functions : {len(candidate.functions)}')
        print(f'  dataflow          : {len(candidate.dataflow)}')
        print(f'  related variables : {len(candidate.related_variables)}')
        print(f'  definitions       : {len(candidate.related_definitions.definitions)}')
        print(f'  context           : {output}')


if __name__ == '__main__':
    main()
