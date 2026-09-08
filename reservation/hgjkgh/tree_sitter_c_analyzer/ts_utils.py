from __future__ import annotations

from collections.abc import Iterable

from tree_sitter import Node

from parsed_file import ParsedFile


DECLARATOR_TYPES = {
    'identifier',
    'field_identifier',
    'type_identifier',
    'pointer_declarator',
    'array_declarator',
    'function_declarator',
    'parenthesized_declarator',
    'attributed_declarator'
}


def walk(node: Node) -> Iterable[Node]:
    yield node
    for child in node.named_children:
        yield from walk(child)


def ancestors(node: Node) -> Iterable[Node]:
    current = node.parent
    while current is not None:
        yield current
        current = current.parent


def nearest(node: Node, types: set[str]) -> Node | None:
    for parent in ancestors(node):
        if parent.type in types:
            return parent
    return None


def node_contains(container: Node, target: Node) -> bool:
    return container.start_byte <= target.start_byte and target.end_byte <= container.end_byte


def declarator_name(node: Node | None, parsed_file: ParsedFile) -> str | None:
    if node is None:
        return None

    if node.type in {'identifier', 'field_identifier', 'type_identifier'}:
        return parsed_file.node_text(node)

    preferred = node.child_by_field_name('declarator')
    if preferred is not None:
        name = declarator_name(preferred, parsed_file)
        if name:
            return name

    for child in node.named_children:
        if child.type in DECLARATOR_TYPES:
            name = declarator_name(child, parsed_file)
            if name:
                return name

    return None


def contains_type(node: Node, node_type: str) -> bool:
    if node.type == node_type:
        return True
    return any(contains_type(child, node_type) for child in node.named_children)


def function_name(function_node: Node, parsed_file: ParsedFile) -> str | None:
    declarator = function_node.child_by_field_name('declarator')
    return declarator_name(declarator, parsed_file)


def containing_function(node: Node, parsed_file: ParsedFile) -> str | None:
    current = node
    while current is not None:
        if current.type == 'function_definition':
            return function_name(current, parsed_file)
        current = current.parent
    return None


def operator_text(node: Node, parsed_file: ParsedFile) -> str | None:
    operator = node.child_by_field_name('operator')
    if operator is not None:
        return parsed_file.node_text(operator)

    source = parsed_file.node_text(node)
    candidates = (
        '>>=', '<<=', '+=', '-=', '*=', '/=', '%=', '&=', '|=', '^=',
        '==', '!=', '>=', '<=', '&&', '||', '++', '--', '=', '>', '<',
        '+', '-', '*', '/', '%', '&', '|', '^', '!', '~'
    )
    for candidate in candidates:
        if candidate in source:
            return candidate
    return None
