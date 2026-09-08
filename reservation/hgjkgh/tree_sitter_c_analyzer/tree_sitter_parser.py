from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, Parser

from parsed_file import ParsedFile


@dataclass
class ParseResult:
    parsed_files: list[ParsedFile] = field(default_factory=list)
    failed_files: list[tuple[Path, str]] = field(default_factory=list)


class TreeSitterProjectParser:
    def __init__(self, parser: Parser) -> None:
        self.parser = parser

    def parse_files(self, files: list[Path]) -> ParseResult:
        result = ParseResult()

        for path in files:
            try:
                text, encoding = self._read_text(path)
                source = text.encode('utf-8')
                tree = self.parser.parse(source)
                error_count = self._count_errors(tree.root_node)
                result.parsed_files.append(
                    ParsedFile(
                        path=path.resolve(),
                        text=text,
                        source=source,
                        tree=tree,
                        encoding=encoding,
                        error_count=error_count
                    )
                )
            except Exception as exc:
                result.failed_files.append((path, str(exc)))

        return result

    @staticmethod
    def _read_text(path: Path) -> tuple[str, str]:
        data = path.read_bytes()

        for encoding in ('utf-8-sig', 'utf-8', 'cp932'):
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                continue

        return data.decode('utf-8', errors='replace'), 'utf-8-replace'

    def _count_errors(self, node: Node) -> int:
        count = 1 if node.type == 'ERROR' or node.is_missing else 0
        for child in node.children:
            count += self._count_errors(child)
        return count
