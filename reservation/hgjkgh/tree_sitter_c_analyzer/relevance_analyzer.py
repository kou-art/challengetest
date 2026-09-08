from __future__ import annotations

from dataclasses import dataclass

from symbol_index import SymbolDefinition


@dataclass
class RankedDefinition:
    definition: SymbolDefinition
    score: int
    reason: str


class RelevanceAnalyzer:
    def rank(self, candidate) -> list[RankedDefinition]:
        if candidate.related_definitions is None:
            return []

        result = []
        for definition in candidate.related_definitions.definitions:
            key = self._key(definition)
            result.append(
                RankedDefinition(
                    definition=definition,
                    score=candidate.related_definitions.scores.get(key, 10),
                    reason=candidate.related_definitions.reasons.get(key, '関連定義')
                )
            )

        result.sort(
            key=lambda item: (
                -item.score,
                item.definition.file,
                item.definition.start_line,
                item.definition.name
            )
        )
        return result

    @staticmethod
    def _key(definition: SymbolDefinition) -> tuple:
        return (
            definition.kind,
            definition.symbol_id,
            definition.file,
            definition.start_line,
            definition.end_line
        )
