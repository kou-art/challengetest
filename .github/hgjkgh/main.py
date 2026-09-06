from pathlib import Path

from scanner import ProjectScanner
from clang_mannager import ClangManager
from translation_unit_parser import TranslationUnitParser
from variable_analyzer import VariableAnalyzer
from symbol_index import SymbolIndex
from related_definition_analyzer import RelatedDefinitionAnalyzer
from relevance_analyzer import RelevanceAnalyzer
from code_extractor import CodeExtractor
from context_builder import ContextBuilder

def main() -> None:

    # 1. 入力
    project_root = Path(input("Cプロジェクトのルートフォルダ: ").strip()).resolve()
    target_variable = input("調べたい変数名: ").strip()

    if (not project_root.exists()):
        raise FileNotFoundError(f"フォルダが存在しません: {project_root}")
    if (not project_root.is_dir()):
        raise NotADirectoryError(f"フォルダではありません: {project_root}")
    if (not target_variable):
        raise ValueError("変数名が空です。")


    # 2. .c / .h 探索
    scanner = ProjectScanner(project_root)

    project_files = scanner.scan()

    print()
    print("=" * 60)
    print("Project")
    print("=" * 60)
    print(f"Root : {project_files.root}")
    print(f".c   : {len(project_files.c_files)}")
    print(f".h   : {len(project_files.h_files)}")

    # 3. Clang初期化
    clang_manager = ClangManager()
    clang_manager.initialize()
    index = clang_manager.get_index()

    print()
    print("Clang initialization: OK")

    # 4. 全.cをAST解析
    parser = TranslationUnitParser(
        index=index,
        project_root=project_files.root,
        c_files=project_files.c_files,
        h_files=project_files.h_files,
    )

    parse_result = parser.parse_all()

    print()
    print(
        "AST解析成功:"
        f" {len(parse_result.translation_units)}"
        f" / {len(project_files.c_files)}"
    )

    if (not parse_result.translation_units):
        print("解析可能なTranslation Unitがありません。")

        return

    # 5. 対象変数解析
    analyzer = VariableAnalyzer(parse_result.translation_units)
    candidates = analyzer.analyze(target_variable)

    print()
    print("=" * 60)
    print(
        f"Target Variable: "
        f"{target_variable}"
    )
    print("=" * 60)

    if (not candidates):
        print("対象変数は見つかりませんでした。")

        return

    # ============================================================
    # 6. SymbolIndex作成
    # プロジェクト全体から
    # ・関数
    # ・変数
    # ・struct
    # ・enum
    # ・typedef
    # ・macro
    # などを索引化
    # ============================================================
    print()
    print("=" * 60)
    print("Symbol Index")
    print("=" * 60)

    symbol_index = SymbolIndex(
        translation_units=parse_result.translation_units,
        project_root=project_files.root,
    )
    symbol_index.build()
    print(
        f"名前索引 : "
        f"{len(symbol_index.by_name)}"
    )
    print(
        f"USR索引  : "
        f"{len(symbol_index.by_usr)}"
    )

    # 7. 関連定義解析器
    related_analyzer = RelatedDefinitionAnalyzer(symbol_index,parse_result.translation_units)

    # 8. 各Candidateを表示
    for number, candidate in enumerate(candidates,1):
        # ここで関連定義を解析してcandidateへ格納
        candidate.related_definitions = related_analyzer.analyze(candidate)

        # Candidate基本情報
        print()
        print("=" * 60)
        print(f"Candidate {number}")
        print("=" * 60)
        print(f"名前 : {candidate.name}")
        print(f"USR  : {candidate.usr}")
        print(f"Kind : {candidate.kind}")

        # 宣言・定義
        print()
        print("宣言・定義:")

        if (not candidate.declarations):
            print("  なし")
        else:
            for declaration in (candidate.declarations):
                print(
                    f"  "
                    f"{declaration.file}:"
                    f"{declaration.line}"
                    f"  "
                    f"{declaration.type_name}"
                    f"  "
                    f"definition="
                    f"{declaration.is_definition}"
                )

        # 使用関数
        print()
        print("使用関数:")
        if not candidate.functions:
            print("  なし")
        else:
            for function in sorted(candidate.functions):
                print(f"  {function}")

        # 参照箇所
        print()
        print("参照箇所:")

        if not candidate.references:
            print("  なし")
        else:
            for reference in (candidate.references):
                print(
                    f"  "
                    f"{reference.file}:"
                    f"{reference.line}"
                    f"  "
                    f"function="
                    f"{reference.function}"
                )

        # 使用方法
        print()
        print("使用方法:")

        if not candidate.expressions:
            print("  なし")
        else:
            for expression in (candidate.expressions):
                print()
                print(
                    f"  "
                    f"[{expression.operation}]"
                )
                print(
                    f"    function : "
                    f"{expression.function}"
                )
                print(
                    f"    location : "
                    f"{expression.file}:"
                    f"{expression.line}"
                )
                if (expression.operator):
                    print(
                        f"    operator : "
                        f"{expression.operator}"
                    )
                if (expression.side):
                    print(
                        f"    side     : "
                        f"{expression.side}"
                    )

                if (expression.callee):
                    print(
                        f"    callee   : "
                        f"{expression.callee}"
                    )
                if (expression.member):
                    print(
                        f"    member   : "
                        f"{expression.member}"
                    )

                print("    expression:")
                print(
                    f"      "
                    f"{expression.expression}"
                )

        # 値の流れ
        print()
        print("値の流れ:")

        if not candidate.dataflow:
            print("  なし")
        else:
            for flow in (candidate.dataflow):
                print()
                print(
                    f"  "
                    f"[{flow.direction}]"
                )
                print(
                    f"    operation : "
                    f"{flow.operation}"
                )
                print(
                    f"    function  : "
                    f"{flow.function}"
                )
                print(
                    f"    location  : "
                    f"{flow.file}:"
                    f"{flow.line}"
                )

                # 呼び出し先
                if flow.callee:
                    print(
                        f"    callee    : "
                        f"{flow.callee}"
                    )

                # 引数番号
                if (flow.argument_index is not None):
                    print(
                        f"    argument  : "
                        f"{flow.argument_index}"
                    )

                # 式
                print("    expression:")
                print(
                    f"      "
                    f"{flow.expression}"
                )

                # 演算子
                if (flow.operator):
                    print(
                        f"    operator   : "
                        f"{flow.operator}"
                    )

                # 代入値
                if (flow.value_expression):
                    print(
                        f"    value      : "
                        f"{flow.value_expression}"
                    )

                # 条件式
                if (flow.condition_expression):
                    print(
                        f"    condition  : "
                        f"{flow.condition_expression}"
                    )

                # 関連シンボル
                if (flow.related_symbols):
                    print("    related:")

                    for symbol in (flow.related_symbols):
                        print(
                            f"      - "
                            f"{symbol.name}"
                            f" "
                            f"[{symbol.kind}]"
                        )

                        if (symbol.file):
                            print(
                                f"        "
                                f"{symbol.file}:"
                                f"{symbol.line}"
                            )

                # 条件によって影響を受ける処理
                if (flow.effects):
                    print("    effects:")

                    for effect in (flow.effects):
                        print(
                            f"      - "
                            f"{effect.name}"
                            f" "
                            f"[{effect.kind}]"
                        )

                        if (effect.file):
                            print(
                                f"        "
                                f"{effect.file}:"
                                f"{effect.line}"
                            )

        # 関連定義
        print()
        print("関連定義:")

        if (candidate.related_definitions is None):
            print("  なし")
        elif (not candidate.related_definitions.definitions):
            print("  なし")
        else:
            for definition in (candidate.related_definitions.definitions):
                definition_type = ""

                if definition.type_name:
                    definition_type = (
                        f" "
                        f"type="
                        f"{definition.type_name}"
                    )

                print()
                print(
                    f"  "
                    f"[{definition.kind}] "
                    f"{definition.name}"
                    f"{definition_type}"
                )
                print(
                    f"    "
                    f"{definition.file}:"
                    f"{definition.start_line}"
                    f"-"
                    f"{definition.end_line}"
                )
                print(
                    f"    "
                    f"definition="
                    f"{definition.is_definition}"
                )

        # 関連ヘッダ
        print()
        print("関連ヘッダ:")

        if ((candidate.related_definitions is not None)and(candidate.related_definitions.headers)):
            for header in sorted(candidate.related_definitions.headers):
                print(f"  {header}")
        else:
            print("  なし")

        # 関連Cファイル
        print()
        print("関連Cファイル:")

        if ((candidate.related_definitions is not None)and(candidate.related_definitions.source_files)):
            for source in sorted(candidate.related_definitions.source_files):
                print(f"  {source}")
        else:
            print("  なし")

        # ⑩ ノイズ除去・関連度判定
        relevance_analyzer = RelevanceAnalyzer()

        ranked_definitions = relevance_analyzer.analyze(candidate)

        print()
        print("関連コード選択:")

        for ranked in (ranked_definitions):
            print(
                f"  "
                f"{ranked.score:3d}"
                f"  "
                f"{ranked.definition.name}"
                f"  "
                f"{ranked.reason}"
            )


        # 実Cコード取得
        code_extractor = CodeExtractor()
        code_blocks = code_extractor.extract(ranked_definitions)

        # ⑪ トークン制限
        context_builder = ContextBuilder(max_tokens=90000)
        context_result = context_builder.build(candidate=candidate,blocks=code_blocks)

        # ファイル保存
        if (len(candidates) == 1):
            output_file = (project_files.root / "llm_context.txt")
        else:
            output_file = (
                project_files.root
                / (
                    f"llm_context_"
                    f"{number}_"
                    f"{candidate.name}.txt"
                )
            )

        context_builder.save(context_result,output_file)

        print()
        print("=" * 60)
        print("LLM Context")
        print("=" * 60)
        print(
            f"推定トークン数 : "
            f"{context_result.estimated_tokens}"
        )
        print(
            f"採用コード数   : "
            f"{context_result.included_blocks}"
        )
        print(
            f"除外コード数   : "
            f"{context_result.excluded_blocks}"
        )
        print(
            f"保存先         : "
            f"{output_file}"
        )
        
# 実行
if __name__ == "__main__":
    main()