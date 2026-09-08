from __future__ import annotations

import sys
from pathlib import Path

from tree_sitter_manager import TreeSitterManager
from tree_sitter_parser import TreeSitterProjectParser


def print_tree(node, parsed_file, indent: int = 0) -> None:
    marker = ' ERROR' if node.type == 'ERROR' or node.is_missing else ''
    text = parsed_file.node_text(node).replace('\n', ' ')[:80]
    print(f'{"  " * indent}{node.type} [{node.start_point.row + 1}:{node.start_point.column}] {text}{marker}')
    for child in node.named_children:
        print_tree(child, parsed_file, indent + 1)


def main() -> None:
    if len(sys.argv) != 2:
        print('Usage: python inspect_tree.py <file.c|file.h>')
        return

    path = Path(sys.argv[1]).resolve()
    manager = TreeSitterManager()
    parser = TreeSitterProjectParser(manager.create_parser())
    result = parser.parse_files([path])

    if not result.parsed_files:
        print(result.failed_files)
        return

    parsed_file = result.parsed_files[0]
    print(f'File       : {parsed_file.path}')
    print(f'Encoding   : {parsed_file.encoding}')
    print(f'ERROR nodes: {parsed_file.error_count}')
    print_tree(parsed_file.tree.root_node, parsed_file)


if __name__ == '__main__':
    main()
