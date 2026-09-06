from __future__ import annotations

from dataclasses import dataclass

from symbol_index import SymbolDefinition

@dataclass
class RankedDefinition:
    definition: SymbolDefinition
    score: int
    reason: str

class RelevanceAnalyzer:
    """
    対象変数を説明するための関連定義に優先順位を付ける。
    高:
        対象変数そのもの
        対象変数を直接使用する関数
        代入元
        比較対象
        影響先
    中:
        関連型
    低:
        宣言のみ
    """
    def analyze(self,candidate) -> list[RankedDefinition]:
        if (candidate.related_definitions is None):
            return []

        definitions = candidate.related_definitions.definitions

        # Dataflowに直接出てきた名前
        dataflow_names: set[str] = set()
        effect_names: set[str] = set()

        for flow in candidate.dataflow:
            for symbol in flow.related_symbols:
                dataflow_names.add(symbol.name)

            for effect in flow.effects:
                effect_names.add(effect.name)

            if (flow.callee):
                dataflow_names.add(flow.callee)

        # ========================================================
        # 定義が存在するシンボルを調べる
        # definition=True が存在する場合、
        # 同じシンボルの宣言だけのものは基本的に削除する
        # ========================================================
        symbols_with_definition: set[tuple[str | None, str]] = set()

        for definition in definitions:
            if (definition.is_definition):
                key = (definition.usr,definition.name)
                symbols_with_definition.add(key)

        ranked: list[RankedDefinition] = []
        seen: set[tuple] = set()

        for definition in definitions:
            # 完全重複削除
            duplicate_key = (
                definition.kind,
                definition.name,
                definition.file,
                definition.start_line,
                definition.end_line
            )

            if (duplicate_key in seen):
                continue

            seen.add(duplicate_key)

            # 定義が別に存在する場合は、同一シンボルの宣言だけを削除
            symbol_key = (definition.usr,definition.name)

            if ((not definition.is_definition)and(symbol_key in symbols_with_definition)):
                continue

            # Score
            score = 10
            reason = "関連定義"

            # 対象変数そのもの
            if (definition.usr == candidate.usr):
                score = 100
                reason = "対象変数の定義"
            # 対象変数を直接使用する関数
            elif ((definition.kind == "FUNCTION_DECL")and(definition.name in candidate.functions)):
                score = 95
                reason = "対象変数を直接使用する関数"
            # データフロー上のシンボル
            elif (definition.name in dataflow_names):
                score = 90
                reason = "対象変数の値の流れに直接関係"
            # 条件成立後などの影響先
            elif (definition.name in effect_names):
                score = 85
                reason = "対象変数の値によって影響を受ける処理"
            # macro
            elif (definition.kind == "MACRO_DEFINITION"):
                score = 80
                reason = "関連マクロ"
            # enum
            elif (definition.kind in {"ENUM_DECL","ENUM_CONSTANT_DECL"}):
                score = 75
                reason = "関連enum"
            # struct / union
            elif (definition.kind in {"STRUCT_DECL","UNION_DECL","FIELD_DECL"}):
                score = 70
                reason = "関連データ型"
            # typedef
            elif (definition.kind == "TYPEDEF_DECL"):
                score = 70
                reason = "関連typedef"
            # 宣言しか存在しない関数
            elif ((definition.kind == "FUNCTION_DECL")and(not definition.is_definition)):
                score = 60
                reason = "関連関数の宣言"

            ranked.append(RankedDefinition(definition=definition,score=score,reason=reason))

        # 関連度順
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.definition.file,
                item.definition.start_line
            )
        )

        return ranked