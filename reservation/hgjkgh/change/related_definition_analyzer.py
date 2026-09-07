from __future__ import annotations

from clang import cindex
from dataclasses import dataclass, field
from pathlib import Path

from symbol_index import SymbolDefinition, SymbolIndex

# 結果
@dataclass
class RelatedDefinitionResult:
    definitions: list[SymbolDefinition] = field(default_factory=list)
    headers: set[str] = field(default_factory=set)
    source_files: set[str] = field(default_factory=set)

# Analyzer
class RelatedDefinitionAnalyzer:
    def __init__(self,symbol_index: SymbolIndex,translation_units: list[cindex.TranslationUnit],type_depth: int = 2) -> None:
        self.symbol_index = symbol_index
        self.translation_units = translation_units
        self.type_depth = type_depth

    # 解析
    def analyze(self, candidate) -> RelatedDefinitionResult:
        result = RelatedDefinitionResult()
        seen: set[tuple] = set()

        # 1. 対象変数自身
        self._add_usr(candidate.usr, result, seen, depth=0)

        # 2. 対象変数を直接使っている関数
        for function_name in sorted(candidate.functions):
            self._add_name(function_name, result, seen, depth=0)

        # 3. Dataflowで見つかったシンボル
        for flow in candidate.dataflow:
            # 代入元 / 引数先 / 比較対象
            for symbol in flow.related_symbols:
                self._add_related_symbol(symbol, result, seen)

            # 条件成立時などの影響先
            for symbol in flow.effects:
                self._add_related_symbol(symbol, result, seen)

            # callee名だけ取れている場合
            if (flow.callee):
                self._add_name(flow.callee, result, seen, depth=0)

        # 4. 関連変数と、その変数を直接処理する関数(変更点)
        for variable in candidate.related_variables:
            self._add_usr(variable.usr, result, seen, depth=0)

            for function_name in variable.functions:
                self._add_name(function_name, result, seen, depth=0)

            for flow in variable.dataflow:
                for symbol in flow.related_symbols:
                    self._add_related_symbol(symbol, result, seen)

                for symbol in flow.effects:
                    self._add_related_symbol(symbol, result, seen)

                if (flow.callee):
                    self._add_name(flow.callee, result, seen, depth=0)

        # 5. 対象変数を直接使う関数内の関連シンボル
        extra_functions = self._add_symbols_in_direct_functions(
            candidate.functions,
            candidate.name,
            result,
            seen
        )

        self._add_direct_dependencies_of_functions(
            extra_functions,
            candidate.name,
            result,
            seen
        )

        # 並び替え
        result.definitions.sort(
            key=lambda definition: (
                definition.file,
                definition.start_line,
                definition.kind,
                definition.name
            )
        )

        return result

    # 対象変数を直接使う関数内の関連シンボルを追加
    def _add_symbols_in_direct_functions(self,function_names: set[str],target_name: str,result: RelatedDefinitionResult,seen: set[tuple]) -> set[str]:
        extra_functions: set[str] = set()
        for tu in self.translation_units:
            for cursor in tu.cursor.walk_preorder():
                if (cursor.kind != cindex.CursorKind.FUNCTION_DECL):
                    continue
                if (not cursor.is_definition()):
                    continue
                if (cursor.spelling not in function_names):
                    continue

                self._add_symbols_from_function(cursor,target_name,result,seen,extra_functions)
        return extra_functions

    # 関数内のシンボルを追加
    def _add_symbols_from_function(self,function: cindex.Cursor,target_name: str,result: RelatedDefinitionResult,seen: set[tuple],extra_functions: set[str]) -> None:
        symbol_names: set[str] = set()

        for node in function.walk_preorder():
            if (node.kind not in {
                cindex.CursorKind.CALL_EXPR,
                cindex.CursorKind.DECL_REF_EXPR,
                cindex.CursorKind.MEMBER_REF_EXPR
            }):
                continue

            referenced = node.referenced

            if (referenced is None):
                continue

            name = referenced.spelling

            if ((not name)or(name == target_name)):
                continue

            # ローカル変数と関数引数は関数本体に含まれるため追加しない
            if (referenced.kind in {
                cindex.CursorKind.PARM_DECL,
                cindex.CursorKind.VAR_DECL
            }):
                parent = referenced.semantic_parent

                if ((parent is not None)and(parent.kind == cindex.CursorKind.FUNCTION_DECL)):
                    continue

            usr = referenced.get_usr()

            if (usr):
                definitions = self.symbol_index.find_by_usr(usr)

                if (definitions):
                    for definition in definitions:
                        self._add_definition(definition, result, seen, depth=0)

                        if (definition.kind == "FUNCTION_DECL"):
                            extra_functions.add(definition.name)
                    continue

            symbol_names.add(name)

        # macroは通常のAST参照で取得できない場合があるためトークンも確認
        for token in function.get_tokens():
            name = token.spelling

            if ((not name)or(name == target_name)):
                continue

            definitions = self.symbol_index.find_by_name(name)

            if (any(definition.kind == "MACRO_DEFINITION" for definition in definitions)):
                symbol_names.add(name)

        for name in symbol_names:
            definitions = self.symbol_index.find_by_name(name)

            for definition in definitions:
                self._add_definition(definition, result, seen, depth=0)

                if (definition.kind == "FUNCTION_DECL"):
                    extra_functions.add(definition.name)
    # 追加取得した関数の直接依存定義を追加
    def _add_direct_dependencies_of_functions(self,function_names: set[str],target_name: str,result: RelatedDefinitionResult,seen: set[tuple]) -> None:
        for tu in self.translation_units:
            for cursor in tu.cursor.walk_preorder():
                if (cursor.kind != cindex.CursorKind.FUNCTION_DECL):
                    continue
                if (not cursor.is_definition()):
                    continue
                if (cursor.spelling not in function_names):
                    continue

                self._add_direct_dependencies_from_function(
                    cursor,
                    target_name,
                    result,
                    seen
                )


    # 関数内の直接依存定義を追加
    def _add_direct_dependencies_from_function(self,function: cindex.Cursor,target_name: str,result: RelatedDefinitionResult,seen: set[tuple]) -> None:
        for node in function.walk_preorder():
            if (node.kind not in {
                cindex.CursorKind.CALL_EXPR,
                cindex.CursorKind.DECL_REF_EXPR,
                cindex.CursorKind.MEMBER_REF_EXPR
            }):
                continue

            referenced = node.referenced

            if (referenced is None):
                continue

            name = referenced.spelling

            if ((not name)or(name == target_name)):
                continue

            if (referenced.kind in {
                cindex.CursorKind.PARM_DECL,
                cindex.CursorKind.VAR_DECL
            }):
                parent = referenced.semantic_parent

                if ((parent is not None)and(parent.kind == cindex.CursorKind.FUNCTION_DECL)):
                    continue

            usr = referenced.get_usr()

            if (usr):
                definitions = self.symbol_index.find_by_usr(usr)

                if (definitions):
                    for definition in definitions:
                        self._add_definition(definition, result, seen, depth=0)

                    continue

            self._add_name(name, result, seen, depth=0)

        # macro
        for token in function.get_tokens():
            name = token.spelling

            if ((not name)or(name == target_name)):
                continue

            for definition in self.symbol_index.find_by_name(name):
                if (definition.kind == "MACRO_DEFINITION"):
                    self._add_definition(definition, result, seen, depth=0)

    # RelatedSymbolを解決
    def _add_related_symbol(self,symbol,result: RelatedDefinitionResult,seen: set[tuple]) -> None:
        # USRがあるならUSRを最優先
        if (symbol.usr):
            definitions = self.symbol_index.find_by_usr(symbol.usr)

            if (definitions):
                for definition in definitions:
                    self._add_definition(definition, result, seen, depth=0)

                return

        # macroなどUSRなし
        self._add_name(symbol.name, result, seen, depth=0)

    # USRから追加
    def _add_usr(self,usr: str,result: RelatedDefinitionResult,seen: set[tuple],depth: int) -> None:
        for definition in self.symbol_index.find_by_usr(usr):
            self._add_definition(definition, result, seen, depth)

    # 名前から追加
    def _add_name(self,name: str,result: RelatedDefinitionResult,seen: set[tuple],depth: int) -> None:
        for definition in self.symbol_index.find_by_name(name):
            self._add_definition(definition, result, seen, depth)

    # 定義追加
    def _add_definition(self,definition: SymbolDefinition,result: RelatedDefinitionResult,seen: set[tuple],depth: int) -> None:
        key = (
            definition.kind,
            definition.name,
            definition.file,
            definition.start_line,
            definition.end_line
        )

        if (key in seen):
            return

        seen.add(key)
        result.definitions.append(definition)

        # 関連ファイル
        suffix = Path(definition.file).suffix.lower()

        if (suffix == ".h"):
            result.headers.add(definition.file)
        elif (suffix == ".c"):
            result.source_files.add(definition.file)

        # 型だけ再帰的に追う
        if (depth >= self.type_depth):
            return

        for type_usr in definition.related_type_usrs:
            self._add_usr(type_usr, result, seen, depth + 1)