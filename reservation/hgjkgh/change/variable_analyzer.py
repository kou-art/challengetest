#変更した
from __future__ import annotations

from dataclasses import dataclass, field

from clang import cindex
from clang.cindex import Cursor, CursorKind

from expression_analyzer import ExpressionAnalyzer,ExpressionRecord

from dataflow_analyzer import DataflowAnalyzer,DataflowRecord

from related_definition_analyzer import RelatedDefinitionResult
from related_variable_analyzer import RelatedVariableAnalysis
from related_variable_analyzer import RelatedVariableAnalyzer

@dataclass
class VariableDeclaration:
    name: str
    usr: str
    kind: str
    type_name: str
    file: str
    line: int
    is_definition: bool

@dataclass
class VariableReference:
    file: str
    line: int
    function: str | None

@dataclass
class VariableCandidate:
    name: str
    usr: str
    kind: str
    declarations: list[VariableDeclaration] = field(default_factory=list)
    references: list[VariableReference] = field(default_factory=list)
    functions: set[str] = field(default_factory=set)
    expressions: list[ExpressionRecord] = field(default_factory=list)
    dataflow: list[DataflowRecord] = field(default_factory=list)
    related_definitions: (RelatedDefinitionResult | None) = None
    related_variables: list[RelatedVariableAnalysis] = field(default_factory=list)

class VariableAnalyzer:
    TARGET_DECLARATION_KINDS = {
        CursorKind.VAR_DECL,
        CursorKind.FIELD_DECL
    }
    TARGET_REFERENCE_KINDS = {
        CursorKind.DECL_REF_EXPR,
        CursorKind.MEMBER_REF_EXPR
    }

    def __init__(self,translation_units: list[cindex.TranslationUnit]) -> None:
        self.translation_units = translation_units
        self.expression_analyzer = ExpressionAnalyzer()
        self.dataflow_analyzer = DataflowAnalyzer(translation_units)
        self.related_variable_analyzer = RelatedVariableAnalyzer(translation_units)

    # メイン
    def analyze(self,target_variable: str) -> list[VariableCandidate]:
        candidates: dict[str,VariableCandidate] = {}

        # 宣言・定義
        for tu in self.translation_units:
            self._collect_declarations(cursor=tu.cursor,target_variable=target_variable,candidates=candidates)

        if (not candidates):
            return []

        # 参照
        for tu in self.translation_units:
            self._collect_references(cursor=tu.cursor,target_variable=target_variable,candidates=candidates,current_function=None)

        # 式解析
        for candidate in (candidates.values()):
            candidate.expressions = self.expression_analyzer.analyze(
                    translation_units=self.translation_units,
                    target_name=target_variable,
                    target_usr=candidate.usr
                )
            candidate.dataflow = self.dataflow_analyzer.analyze(
                    target_name=target_variable,
                    target_usr=candidate.usr
                )
            candidate.related_variables = self.related_variable_analyzer.analyze(
                    candidate.dataflow,
                    candidate.usr
                )

        return list(candidates.values())

    # 宣言
    def _collect_declarations(self,cursor: Cursor,target_variable: str,candidates: dict[str,VariableCandidate]) -> None:
        if ((cursor.kind in self.TARGET_DECLARATION_KINDS)and(cursor.spelling == target_variable)):
            usr = cursor.get_usr()

            if (usr):
                candidate = candidates.setdefault(
                        usr,
                        VariableCandidate(
                            name=target_variable,
                            usr=usr,
                            kind=cursor.kind.name
                        )
                    )

                if (cursor.location.file):
                    is_definition = False
                    if (cursor.kind == CursorKind.VAR_DECL):
                        is_definition = cursor.is_definition()
                    elif (cursor.kind == CursorKind.FIELD_DECL):
                        # struct fieldは宣言そのもの
                        is_definition = True

                    candidate.declarations.append(
                        VariableDeclaration(
                            name=target_variable,
                            usr=usr,
                            kind=cursor.kind.name,
                            type_name=cursor.type.spelling,
                            file=cursor.location.file.name,
                            line=cursor.location.line,
                            is_definition=is_definition,
                        )
                    )

        for child in cursor.get_children():
            self._collect_declarations(child,target_variable,candidates)

    # 参照
    def _collect_references(self,cursor: Cursor,target_variable: str,candidates: dict[str,VariableCandidate],current_function: Cursor | None) -> None:
        if ((cursor.kind == CursorKind.FUNCTION_DECL)and(cursor.is_definition())):
            current_function = cursor

        if ((cursor.kind in self.TARGET_REFERENCE_KINDS)and(cursor.spelling == target_variable)):
            referenced = cursor.referenced

            if (referenced is not None):
                usr = referenced.get_usr()
                candidate = candidates.get(usr)

                if (candidate is not None):
                    function_name = None
                    if (current_function is not None):
                        function_name = current_function.spelling
                        candidate.functions.add(function_name)

                    if (cursor.location.file):
                        candidate.references.append(
                            VariableReference(
                                file=cursor.location.file.name,
                                line=cursor.location.line,
                                function=function_name
                            )
                        )

        for child in cursor.get_children():
            self._collect_references(child,target_variable,candidates,current_function)