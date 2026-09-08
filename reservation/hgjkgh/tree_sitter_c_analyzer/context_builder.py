from __future__ import annotations

from math import ceil
from pathlib import Path

from code_extractor import CodeBlock


class ContextBuilder:
    def __init__(self, max_tokens: int = 90000) -> None:
        self.max_tokens = max_tokens

    def build(self, candidate, blocks: list[CodeBlock]) -> str:
        parts = [
            '=' * 60,
            'TARGET VARIABLE',
            '=' * 60,
            candidate.name,
            '',
            '=' * 60,
            'TARGET VARIABLE USAGES',
            '=' * 60,
            ''
        ]

        if candidate.dataflow:
            for flow in candidate.dataflow:
                parts.append(self._usage_line(flow))
        else:
            parts.append('- なし')

        parts.extend(['', '=' * 60, 'RELATED VARIABLES', '=' * 60, ''])
        if candidate.related_variables:
            for variable in candidate.related_variables:
                reasons = ', '.join(sorted(variable.reasons))
                parts.append(f'[{variable.name}] {reasons}')
                if variable.dataflow:
                    for flow in variable.dataflow:
                        parts.append(f'  {self._usage_line(flow)}')
                else:
                    parts.append('  - 使用箇所なし')
                parts.append('')
        else:
            parts.append('- なし')

        parts.extend(['=' * 60, 'RELATED SOURCE CODE', '=' * 60, ''])
        header = '\n'.join(parts)
        selected = [header]
        token_count = self.estimate_tokens(header)

        for block in blocks:
            text = self._format_block(block)
            tokens = self.estimate_tokens(text)
            if token_count + tokens > self.max_tokens:
                continue
            selected.append(text)
            token_count += tokens

        return '\n'.join(selected).rstrip() + '\n'

    def save(self, path: Path, candidate, blocks: list[CodeBlock]) -> Path:
        text = self.build(candidate, blocks)
        path.write_text(text, encoding='utf-8')
        return path

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return ceil(len(text) / 2)

    @staticmethod
    def _usage_line(flow) -> str:
        function = flow.function or '<global>'
        return f'- {flow.file}:{flow.line} [{function}] {flow.operation}: {flow.expression}'

    @staticmethod
    def _format_block(block: CodeBlock) -> str:
        return (
            f'----- FILE: {block.file}\n'
            f'----- LINES: {block.start_line}-{block.end_line}\n'
            f'----- PRIORITY: {block.score}\n'
            f'----- REASON: {block.reason}\n\n'
            f'{block.code}\n'
        )
