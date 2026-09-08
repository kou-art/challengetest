from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node

from parsed_file import ParsedFile
from preprocessor_scanner import PreprocessorScanner
from ts_utils import contains_type, containing_function, declarator_name, function_name, walk


@dataclass
class SymbolDefinition:
    name: str
    symbol_id: str
    kind: str
    file: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    scope: str
    type_name: str | None = None
    is_definition: bool = False
    related_type_names: set[str] = field(default_factory=set)


class SymbolIndex:
    VARIABLE_KINDS = {'VAR_DECL', 'FIELD_DECL', 'PARM_DECL'}
    TYPE_KINDS = {'STRUCT_DECL', 'UNION_DECL', 'ENUM_DECL', 'TYPEDEF_DECL'}

    def __init__(self, parsed_files: list[ParsedFile], project_root: Path) -> None:
        self.parsed_files = parsed_files
        self.project_root = project_root.resolve()
        self.by_id: dict[str, list[SymbolDefinition]] = {}
        self.by_name: dict[str, list[SymbolDefinition]] = {}
        self.declaration_positions: set[tuple[str, int, int]] = set()
        self.file_map = {str(parsed_file.path): parsed_file for parsed_file in parsed_files}
        self.preprocessor = PreprocessorScanner()

    def build(self) -> None:
        for parsed_file in self.parsed_files:
            self._index_file(parsed_file)
            macros, _ = self.preprocessor.scan(parsed_file)
            for macro in macros:
                self._add(
                    SymbolDefinition(
                        name=macro.name,
                        symbol_id=f'macro::{macro.name}',
                        kind='MACRO_DEFINITION',
                        file=macro.file,
                        start_line=macro.start_line,
                        end_line=macro.end_line,
                        start_byte=self._line_start_byte(parsed_file, macro.start_line),
                        end_byte=self._line_end_byte(parsed_file, macro.end_line),
                        scope='<global>',
                        is_definition=True
                    )
                )

    def find_by_id(self, symbol_id: str) -> list[SymbolDefinition]:
        return list(self.by_id.get(symbol_id, []))

    def find_by_name(self, name: str) -> list[SymbolDefinition]:
        return list(self.by_name.get(name, []))

    def find_variables(self, name: str) -> list[SymbolDefinition]:
        return [definition for definition in self.find_by_name(name) if definition.kind in self.VARIABLE_KINDS]


    def best_definition(self, symbol_id: str) -> SymbolDefinition | None:
        definitions = self.find_by_id(symbol_id)
        defined = [definition for definition in definitions if definition.is_definition]
        if defined:
            return defined[0]
        return definitions[0] if definitions else None

    def find_unique_by_name(self, name: str, kinds: set[str] | None = None) -> SymbolDefinition | None:
        definitions = self.find_by_name(name)
        if kinds is not None:
            definitions = [definition for definition in definitions if definition.kind in kinds]

        symbol_ids = {definition.symbol_id for definition in definitions}
        if len(symbol_ids) != 1:
            return None

        return self.best_definition(next(iter(symbol_ids)))

    def find_function_definition(self, name: str, file: str | None = None) -> SymbolDefinition | None:
        definitions = [
            definition for definition in self.find_by_name(name)
            if definition.kind == 'FUNCTION_DECL' and definition.is_definition
        ]
        if file is not None:
            file_name = str(Path(file).resolve())
            local = [definition for definition in definitions if str(Path(definition.file).resolve()) == file_name]
            if local:
                return local[0]

        if len(definitions) == 1:
            return definitions[0]

        globals_ = [definition for definition in definitions if definition.scope == '<global>']
        if len(globals_) == 1:
            return globals_[0]

        return None

    def find_function_node(self, parsed_file: ParsedFile, name: str) -> Node | None:
        for node in walk(parsed_file.tree.root_node):
            if node.type != 'function_definition':
                continue
            if function_name(node, parsed_file) == name:
                return node
        return None

    def is_constant_definition(self, definition: SymbolDefinition) -> bool:
        if definition.kind in {'MACRO_DEFINITION', 'ENUM_CONSTANT_DECL'}:
            return True
        if definition.kind != 'VAR_DECL':
            return False

        parsed_file = self.parsed_file_for(definition.file)
        if parsed_file is None:
            return False

        source = parsed_file.source[definition.start_byte:definition.end_byte].decode('utf-8', errors='replace')
        return 'const' in source.replace('\n', ' ').replace('\t', ' ').split()

    def parsed_file_for(self, file: str) -> ParsedFile | None:
        return self.file_map.get(str(Path(file).resolve()))

    def is_declaration_node(self, parsed_file: ParsedFile, node: Node) -> bool:
        return (str(parsed_file.path), node.start_byte, node.end_byte) in self.declaration_positions

    def resolve_reference_candidates(self, parsed_file: ParsedFile, node: Node) -> list[SymbolDefinition]:
        name = parsed_file.node_text(node)
        if not name:
            return []

        function = containing_function(node, parsed_file)
        file_name = str(parsed_file.path)

        if node.type == 'field_identifier':
            fields = [definition for definition in self.find_by_name(name) if definition.kind == 'FIELD_DECL']
            return self._best_definitions_by_symbol_id(fields)

        if self._is_call_function_node(node):
            functions = [definition for definition in self.find_by_name(name) if definition.kind == 'FUNCTION_DECL']
            local = [definition for definition in functions if definition.file == file_name]
            if local:
                return self._best_definitions_by_symbol_id(local)

            defined = [definition for definition in functions if definition.is_definition]
            if defined:
                return self._best_definitions_by_symbol_id(defined)

            return self._best_definitions_by_symbol_id(functions)

        candidates = self.find_by_name(name)

        if function:
            function_scope = self._function_scope(file_name, function)
            local = [
                definition for definition in candidates
                if definition.kind in {'VAR_DECL', 'PARM_DECL'} and definition.scope == function_scope
            ]
            if local:
                return self._best_definitions_by_symbol_id(local)

        file_static = [
            definition for definition in candidates
            if definition.kind == 'VAR_DECL'
            and definition.scope == '<file>'
            and definition.file == file_name
        ]
        if file_static:
            return self._best_definitions_by_symbol_id(file_static)

        globals_ = [
            definition for definition in candidates
            if definition.kind == 'VAR_DECL' and definition.scope == '<global>'
        ]
        if globals_:
            return self._best_definitions_by_symbol_id(globals_)

        enum_values = [definition for definition in candidates if definition.kind == 'ENUM_CONSTANT_DECL']
        if enum_values:
            return self._best_definitions_by_symbol_id(enum_values)

        macros = [definition for definition in candidates if definition.kind == 'MACRO_DEFINITION']
        if macros:
            return self._best_definitions_by_symbol_id(macros)

        return self._best_definitions_by_symbol_id(candidates)

    def resolve_reference(self, parsed_file: ParsedFile, node: Node) -> SymbolDefinition | None:
        candidates = self.resolve_reference_candidates(parsed_file, node)
        return candidates[0] if len(candidates) == 1 else None

    def _best_definitions_by_symbol_id(self, definitions: list[SymbolDefinition]) -> list[SymbolDefinition]:
        result = []
        seen = set()

        for definition in definitions:
            if definition.symbol_id in seen:
                continue
            seen.add(definition.symbol_id)
            preferred = self.best_definition(definition.symbol_id)
            if preferred is not None:
                result.append(preferred)

        return result

    def matches_reference(self, candidate: SymbolDefinition, parsed_file: ParsedFile, node: Node) -> bool:
        if parsed_file.node_text(node) != candidate.name:
            return False

        return any(
            definition.symbol_id == candidate.symbol_id
            for definition in self.resolve_reference_candidates(parsed_file, node)
        )

    def _index_file(self, parsed_file: ParsedFile) -> None:
        root = parsed_file.tree.root_node
        self._visit(parsed_file, root, current_function=None, current_type=None)

    def _visit(
        self,
        parsed_file: ParsedFile,
        node: Node,
        current_function: str | None,
        current_type: str | None
    ) -> None:
        if node.type == 'function_definition':
            name = function_name(node, parsed_file)
            if name:
                self._index_function(parsed_file, node, name, is_definition=True)
                self._index_parameters(parsed_file, node, name)
                body = node.child_by_field_name('body')
                if body is not None:
                    self._visit(parsed_file, body, current_function=name, current_type=current_type)
            return

        if node.type in {'struct_specifier', 'union_specifier', 'enum_specifier'}:
            type_name = self._type_name(node, parsed_file)
            kind = {
                'struct_specifier': 'STRUCT_DECL',
                'union_specifier': 'UNION_DECL',
                'enum_specifier': 'ENUM_DECL'
            }[node.type]
            if type_name:
                self._add_node_definition(parsed_file, node, type_name, kind, f'type::{kind}::{type_name}', '<global>', True)
            next_type = type_name or current_type or f'<anonymous:{node.start_point.row + 1}>'
            for child in node.named_children:
                self._visit(parsed_file, child, current_function=current_function, current_type=next_type)
            return

        if node.type == 'enumerator':
            name_node = node.child_by_field_name('name')
            if name_node is not None:
                name = parsed_file.node_text(name_node)
                self._add_node_definition(
                    parsed_file,
                    node,
                    name,
                    'ENUM_CONSTANT_DECL',
                    f'enum_value::{current_type or "<anonymous>"}::{name}',
                    current_type or '<enum>',
                    True
                )
            return

        if node.type == 'field_declaration':
            self._index_field_declaration(parsed_file, node, current_type)
            return

        if node.type == 'type_definition':
            self._index_typedef(parsed_file, node)

        if node.type == 'declaration':
            self._index_declaration(parsed_file, node, current_function)

        for child in node.named_children:
            self._visit(parsed_file, child, current_function=current_function, current_type=current_type)

    def _index_function(self, parsed_file: ParsedFile, node: Node, name: str, is_definition: bool) -> None:
        source = parsed_file.node_text(node)
        is_static = self._has_storage_class(source, 'static')
        symbol_id = f'file_function::{parsed_file.path}::{name}' if is_static else f'function::{name}'
        scope = '<file>' if is_static else '<global>'
        related_types = self._collect_type_names(node, parsed_file)
        self._add_node_definition(
            parsed_file,
            node,
            name,
            'FUNCTION_DECL',
            symbol_id,
            scope,
            is_definition,
            related_type_names=related_types
        )

    def _index_parameters(self, parsed_file: ParsedFile, function_node: Node, function: str) -> None:
        declarator = function_node.child_by_field_name('declarator')
        if declarator is None:
            return

        for node in walk(declarator):
            if node.type != 'parameter_declaration':
                continue
            declaration = node.child_by_field_name('declarator')
            name = declarator_name(declaration, parsed_file)
            if not name:
                continue
            scope = self._function_scope(str(parsed_file.path), function)
            symbol_id = f'param::{scope}::{name}'
            self._add_node_definition(
                parsed_file,
                node,
                name,
                'PARM_DECL',
                symbol_id,
                scope,
                True,
                related_type_names=self._collect_type_names(node, parsed_file)
            )
            if declaration is not None:
                name_node = self._find_name_node(declaration, parsed_file, name)
                if name_node is not None:
                    self._mark_declaration(parsed_file, name_node)

    def _index_declaration(self, parsed_file: ParsedFile, node: Node, current_function: str | None) -> None:
        for declarator, value in self._declaration_items(node):
            name = declarator_name(declarator, parsed_file)
            if not name:
                continue

            if contains_type(declarator, 'function_declarator'):
                self._index_function(parsed_file, node, name, is_definition=False)
                name_node = self._find_name_node(declarator, parsed_file, name)
                if name_node is not None:
                    self._mark_declaration(parsed_file, name_node)
                continue

            source = parsed_file.node_text(node)
            if current_function:
                scope = self._function_scope(str(parsed_file.path), current_function)
                symbol_id = f'local::{scope}::{name}'
            elif self._has_storage_class(source, 'static'):
                scope = '<file>'
                symbol_id = f'file_var::{parsed_file.path}::{name}'
            else:
                scope = '<global>'
                symbol_id = f'global_var::{name}'

            is_definition = 'extern' not in source.split()
            self._add_node_definition(
                parsed_file,
                node,
                name,
                'VAR_DECL',
                symbol_id,
                scope,
                is_definition,
                related_type_names=self._collect_type_names(node, parsed_file)
            )
            name_node = self._find_name_node(declarator, parsed_file, name)
            if name_node is not None:
                self._mark_declaration(parsed_file, name_node)

    def _index_field_declaration(self, parsed_file: ParsedFile, node: Node, current_type: str | None) -> None:
        scope = f'type::{current_type or "<anonymous>"}'
        for child in node.named_children:
            if child.type not in {
                'field_identifier', 'pointer_declarator', 'array_declarator',
                'function_declarator', 'parenthesized_declarator', 'attributed_declarator'
            }:
                continue
            name = declarator_name(child, parsed_file)
            if not name:
                continue
            symbol_id = f'field::{current_type or "<anonymous>"}::{name}'
            self._add_node_definition(
                parsed_file,
                node,
                name,
                'FIELD_DECL',
                symbol_id,
                scope,
                True,
                related_type_names=self._collect_type_names(node, parsed_file)
            )
            name_node = self._find_name_node(child, parsed_file, name)
            if name_node is not None:
                self._mark_declaration(parsed_file, name_node)

    def _index_typedef(self, parsed_file: ParsedFile, node: Node) -> None:
        declarator = node.child_by_field_name('declarator')
        name = declarator_name(declarator, parsed_file)
        if not name:
            for child in reversed(node.named_children):
                if child.type in {'type_identifier', 'identifier'}:
                    name = parsed_file.node_text(child)
                    declarator = child
                    break
        if not name:
            return

        self._add_node_definition(
            parsed_file,
            node,
            name,
            'TYPEDEF_DECL',
            f'type::TYPEDEF_DECL::{name}',
            '<global>',
            True,
            related_type_names=self._collect_type_names(node, parsed_file) - {name}
        )
        if declarator is not None:
            name_node = self._find_name_node(declarator, parsed_file, name)
            if name_node is not None:
                self._mark_declaration(parsed_file, name_node)

    def _add_node_definition(
        self,
        parsed_file: ParsedFile,
        node: Node,
        name: str,
        kind: str,
        symbol_id: str,
        scope: str,
        is_definition: bool,
        related_type_names: set[str] | None = None
    ) -> None:
        self._add(
            SymbolDefinition(
                name=name,
                symbol_id=symbol_id,
                kind=kind,
                file=str(parsed_file.path),
                start_line=node.start_point.row + 1,
                end_line=node.end_point.row + 1,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                scope=scope,
                type_name=None,
                is_definition=is_definition,
                related_type_names=related_type_names or set()
            )
        )

    def _add(self, definition: SymbolDefinition) -> None:
        key = (
            definition.kind,
            definition.symbol_id,
            definition.file,
            definition.start_line,
            definition.end_line
        )
        existing = {
            (item.kind, item.symbol_id, item.file, item.start_line, item.end_line)
            for item in self.by_id.get(definition.symbol_id, [])
        }
        if key in existing:
            return
        self.by_id.setdefault(definition.symbol_id, []).append(definition)
        self.by_name.setdefault(definition.name, []).append(definition)

    def _declaration_items(self, node: Node) -> list[tuple[Node, Node | None]]:
        result: list[tuple[Node, Node | None]] = []
        declarator_types = {
            'identifier', 'pointer_declarator', 'array_declarator', 'function_declarator',
            'parenthesized_declarator', 'attributed_declarator', 'init_declarator'
        }
        for child in node.named_children:
            if child.type not in declarator_types:
                continue
            if child.type == 'init_declarator':
                declarator = child.child_by_field_name('declarator')
                value = child.child_by_field_name('value')
                if declarator is not None:
                    result.append((declarator, value))
            else:
                result.append((child, None))
        return result

    def declaration_items(self, node: Node) -> list[tuple[Node, Node | None]]:
        return self._declaration_items(node)

    def declared_symbol(self, parsed_file: ParsedFile, declarator: Node) -> SymbolDefinition | None:
        name = declarator_name(declarator, parsed_file)
        if not name:
            return None
        name_node = self._find_name_node(declarator, parsed_file, name)
        if name_node is None:
            return None
        candidates = self.find_by_name(name)
        for definition in candidates:
            if definition.file != str(parsed_file.path):
                continue
            if definition.start_line <= name_node.start_point.row + 1 <= definition.end_line:
                return definition
        return None

    def _collect_type_names(self, node: Node, parsed_file: ParsedFile) -> set[str]:
        result = set()
        for child in walk(node):
            if child.type == 'type_identifier':
                result.add(parsed_file.node_text(child))
            elif child.type in {'struct_specifier', 'union_specifier', 'enum_specifier'}:
                name = self._type_name(child, parsed_file)
                if name:
                    result.add(name)
        return result

    @staticmethod
    def _function_scope(file: str, function: str) -> str:
        return f'{file}::{function}'

    @staticmethod
    def _has_storage_class(source: str, word: str) -> bool:
        return word in source.replace('\n', ' ').replace('\t', ' ').split()

    @staticmethod
    def _is_call_function_node(node: Node) -> bool:
        parent = node.parent
        if parent is None or parent.type != 'call_expression':
            return False
        function = parent.child_by_field_name('function')
        return function is not None and function.start_byte == node.start_byte and function.end_byte == node.end_byte

    def _type_name(self, node: Node, parsed_file: ParsedFile) -> str | None:
        name = node.child_by_field_name('name')
        if name is not None:
            return parsed_file.node_text(name)
        for child in node.named_children:
            if child.type == 'type_identifier':
                return parsed_file.node_text(child)
        return None

    def _find_name_node(self, node: Node, parsed_file: ParsedFile, name: str) -> Node | None:
        for child in walk(node):
            if child.type in {'identifier', 'field_identifier', 'type_identifier'} and parsed_file.node_text(child) == name:
                return child
        return None

    def _mark_declaration(self, parsed_file: ParsedFile, node: Node) -> None:
        self.declaration_positions.add((str(parsed_file.path), node.start_byte, node.end_byte))

    @staticmethod
    def _line_start_byte(parsed_file: ParsedFile, line: int) -> int:
        if line <= 1:
            return 0
        encoded = ''.join(parsed_file.text.splitlines(keepends=True)[:line - 1]).encode('utf-8')
        return len(encoded)

    @staticmethod
    def _line_end_byte(parsed_file: ParsedFile, line: int) -> int:
        encoded = ''.join(parsed_file.text.splitlines(keepends=True)[:line]).encode('utf-8')
        return len(encoded)
