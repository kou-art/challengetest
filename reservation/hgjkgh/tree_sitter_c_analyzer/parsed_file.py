from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node, Tree


@dataclass
class ParsedFile:
    path: Path
    text: str
    source: bytes
    tree: Tree
    encoding: str
    error_count: int

    def node_text(self, node: Node) -> str:
        return self.source[node.start_byte:node.end_byte].decode('utf-8', errors='replace')

    def line_text(self, line: int) -> str:
        lines = self.text.splitlines()
        if 1 <= line <= len(lines):
            return lines[line - 1]
        return ''
