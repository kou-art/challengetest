from __future__ import annotations

import tree_sitter_c
from tree_sitter import Language, Parser


class TreeSitterManager:
    def __init__(self) -> None:
        self.language = Language(tree_sitter_c.language())

    def create_parser(self) -> Parser:
        return Parser(self.language)
