from __future__ import annotations

from dataclasses import dataclass

from parsed_file import ParsedFile
from relevance_analyzer import RankedDefinition


@dataclass
class CodeBlock:
    file: str
    start_line: int
    end_line: int
    score: int
    reason: str
    code: str


class CodeExtractor:
    def __init__(self, parsed_files: list[ParsedFile], max_leading_comment_lines: int = 50) -> None:
        self.file_map = {str(parsed_file.path): parsed_file for parsed_file in parsed_files}
        self.max_leading_comment_lines = max_leading_comment_lines

    def extract(self, ranked_definitions: list[RankedDefinition]) -> list[CodeBlock]:
        blocks: list[CodeBlock] = []
        seen = set()

        for item in ranked_definitions:
            definition = item.definition
            parsed_file = self.file_map.get(definition.file)
            if parsed_file is None:
                continue

            if definition.kind == 'MACRO_DEFINITION':
                start = self._find_leading_comment_start(
                    parsed_file,
                    definition.start_line,
                    include_preprocessor=False
                )
            else:
                start = self._find_leading_comment_start(parsed_file, definition.start_line)

            end = definition.end_line
            key = (definition.file, start, end)
            if key in seen:
                continue
            seen.add(key)

            lines = parsed_file.text.splitlines()
            code = '\n'.join(lines[start - 1:end])
            blocks.append(
                CodeBlock(
                    file=definition.file,
                    start_line=start,
                    end_line=end,
                    score=item.score,
                    reason=item.reason,
                    code=code
                )
            )

        return self._remove_contained(blocks)

    def _find_leading_comment_start(
        self,
        parsed_file: ParsedFile,
        start_line: int,
        include_preprocessor: bool = True
    ) -> int:
        lines = parsed_file.text.splitlines()
        index = start_line - 2
        if index < 0:
            return start_line
        if not lines[index].strip():
            return start_line

        minimum = max(0, start_line - 1 - self.max_leading_comment_lines)
        stripped = lines[index].strip()

        if include_preprocessor and stripped.startswith('#'):
            while index >= minimum:
                current = lines[index].strip()
                if not current or not current.startswith('#'):
                    break
                index -= 1
            return index + 2

        if stripped.startswith('//'):
            while index >= minimum and lines[index].strip().startswith('//'):
                index -= 1
            return index + 2

        if stripped.endswith('*/'):
            while index >= minimum:
                if '/*' in lines[index]:
                    return index + 1
                if not lines[index].strip():
                    break
                index -= 1

        return start_line

    @staticmethod
    def _remove_contained(blocks: list[CodeBlock]) -> list[CodeBlock]:
        result: list[CodeBlock] = []

        for block in blocks:
            contained = False
            for other in blocks:
                if block is other or block.file != other.file:
                    continue
                if (
                    other.start_line <= block.start_line
                    and other.end_line >= block.end_line
                    and (other.start_line < block.start_line or other.end_line > block.end_line)
                ):
                    contained = True
                    break
            if not contained:
                result.append(block)

        result.sort(key=lambda block: (-block.score, block.file, block.start_line))
        return result
