from __future__ import annotations

from tree_sitter import Node

from analysis_models import DataflowRecord, RelatedSymbol
from parsed_file import ParsedFile
from symbol_index import SymbolDefinition, SymbolIndex
from ts_utils import containing_function, nearest, node_contains, operator_text, walk


class DataflowAnalyzer:
    CONTROL_TYPES = {
        'if_statement',
        'while_statement',
        'do_statement',
        'for_statement',
        'switch_statement',
        'conditional_expression'
    }

    COMPOUND_OPERATORS = {'+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '|=', '^='}

    def __init__(self, parsed_files: list[ParsedFile], symbol_index: SymbolIndex) -> None:
        self.parsed_files = parsed_files
        self.symbol_index = symbol_index

    def analyze(self, target: SymbolDefinition) -> list[DataflowRecord]:
        result: list[DataflowRecord] = []

        for parsed_file in self.parsed_files:
            self._analyze_initializers(parsed_file, target, result)

            for node in walk(parsed_file.tree.root_node):
                if node.type not in {'identifier', 'field_identifier'}:
                    continue
                if self.symbol_index.is_declaration_node(parsed_file, node):
                    continue
                if not self.symbol_index.matches_reference(target, parsed_file, node):
                    continue
                result.extend(self._analyze_reference(parsed_file, node, target))

        return self._deduplicate(result)

    def _analyze_initializers(
        self,
        parsed_file: ParsedFile,
        target: SymbolDefinition,
        result: list[DataflowRecord]
    ) -> None:
        for node in walk(parsed_file.tree.root_node):
            if node.type != 'declaration':
                continue

            for declarator, value in self.symbol_index.declaration_items(node):
                declared = self.symbol_index.declared_symbol(parsed_file, declarator)
                if declared is None or declared.symbol_id != target.symbol_id or value is None:
                    continue

                related = self._collect_symbols(parsed_file, value, exclude_id=target.symbol_id)
                result.append(
                    DataflowRecord(
                        direction='into_target',
                        operation='initialization',
                        function=containing_function(node, parsed_file),
                        file=str(parsed_file.path),
                        line=node.start_point.row + 1,
                        expression=parsed_file.node_text(node),
                        operator='=',
                        value_expression=parsed_file.node_text(value),
                        related_symbols=related
                    )
                )

    def _analyze_reference(
        self,
        parsed_file: ParsedFile,
        target_node: Node,
        target: SymbolDefinition
    ) -> list[DataflowRecord]:
        result: list[DataflowRecord] = []
        file_name = str(parsed_file.path)
        function = containing_function(target_node, parsed_file)
        line = target_node.start_point.row + 1

        update = nearest(target_node, {'update_expression'})
        if update is not None:
            operator = operator_text(update, parsed_file)
            result.append(
                DataflowRecord(
                    direction='target_self_update',
                    operation='increment' if operator == '++' else 'decrement' if operator == '--' else 'update',
                    function=function,
                    file=file_name,
                    line=line,
                    expression=parsed_file.node_text(update),
                    operator=operator
                )
            )
            return result

        assignment = nearest(target_node, {'assignment_expression'})
        if assignment is not None:
            left = assignment.child_by_field_name('left')
            right = assignment.child_by_field_name('right')
            operator = operator_text(assignment, parsed_file)

            if left is not None and node_contains(left, target_node):
                related = self._collect_symbols(parsed_file, right, exclude_id=target.symbol_id) if right is not None else []
                operation = 'compound_assignment' if operator in self.COMPOUND_OPERATORS else 'assignment'
                direction = 'target_self_update' if operator in self.COMPOUND_OPERATORS else 'into_target'
                result.append(
                    DataflowRecord(
                        direction=direction,
                        operation=operation,
                        function=function,
                        file=file_name,
                        line=line,
                        expression=parsed_file.node_text(assignment),
                        operator=operator,
                        value_expression=parsed_file.node_text(right) if right is not None else None,
                        related_symbols=related
                    )
                )
                return result

            if right is not None and node_contains(right, target_node):
                destination = self._primary_symbol(parsed_file, left)
                related = self._collect_symbols(parsed_file, assignment, exclude_id=target.symbol_id)
                result.append(
                    DataflowRecord(
                        direction='from_target',
                        operation='assignment_source',
                        function=function,
                        file=file_name,
                        line=line,
                        expression=parsed_file.node_text(assignment),
                        operator=operator,
                        related_symbols=related,
                        destination_symbol=destination
                    )
                )
                return result

        initializer = nearest(target_node, {'init_declarator'})
        if initializer is not None:
            value = initializer.child_by_field_name('value')
            declarator = initializer.child_by_field_name('declarator')
            if value is not None and declarator is not None and node_contains(value, target_node):
                destination = self._symbol_from_declarator(parsed_file, declarator)
                related = self._collect_symbols(parsed_file, initializer, exclude_id=target.symbol_id)
                result.append(
                    DataflowRecord(
                        direction='from_target',
                        operation='initialization_source',
                        function=function,
                        file=file_name,
                        line=line,
                        expression=parsed_file.node_text(initializer),
                        operator='=',
                        related_symbols=related,
                        destination_symbol=destination
                    )
                )
                return result

        control = self._nearest_control_with_target(target_node)
        if control is not None:
            condition = self._condition_node(control)
            if condition is not None and node_contains(condition, target_node):
                result.append(
                    DataflowRecord(
                        direction='from_target',
                        operation='condition',
                        function=function,
                        file=file_name,
                        line=line,
                        expression=parsed_file.node_text(control),
                        operator=operator_text(condition, parsed_file),
                        condition_expression=parsed_file.node_text(condition),
                        related_symbols=self._collect_symbols(parsed_file, condition, exclude_id=target.symbol_id),
                        effects=self._collect_control_effects(parsed_file, control, condition)
                    )
                )
                return result

        return_statement = nearest(target_node, {'return_statement'})
        if return_statement is not None:
            result.append(
                DataflowRecord(
                    direction='from_target',
                    operation='return',
                    function=function,
                    file=file_name,
                    line=line,
                    expression=parsed_file.node_text(return_statement),
                    related_symbols=self._collect_symbols(parsed_file, return_statement, exclude_id=target.symbol_id)
                )
            )
            return result

        call = nearest(target_node, {'call_expression'})
        if call is not None:
            arguments = call.child_by_field_name('arguments')
            argument_index = self._argument_index(arguments, target_node) if arguments is not None else None
            if argument_index is not None:
                callee = self._callee_name(parsed_file, call)
                argument = self._argument_at(arguments, argument_index)
                address = argument is not None and parsed_file.node_text(argument).lstrip().startswith('&')
                result.append(
                    DataflowRecord(
                        direction='address_to_function' if address else 'from_target',
                        operation='address_argument' if address else 'function_argument',
                        function=function,
                        file=file_name,
                        line=line,
                        expression=parsed_file.node_text(call),
                        operator='&' if address else None,
                        related_symbols=self._collect_symbols(parsed_file, call, exclude_id=target.symbol_id),
                        callee=callee,
                        argument_index=argument_index
                    )
                )
                return result

        statement = nearest(target_node, {'expression_statement', 'declaration'})
        result.append(
            DataflowRecord(
                direction='from_target',
                operation='read',
                function=function,
                file=file_name,
                line=line,
                expression=parsed_file.node_text(statement or target_node),
                related_symbols=self._collect_symbols(parsed_file, statement or target_node, exclude_id=target.symbol_id)
            )
        )
        return result

    def _collect_symbols(
        self,
        parsed_file: ParsedFile,
        node: Node | None,
        exclude_id: str | None = None
    ) -> list[RelatedSymbol]:
        if node is None:
            return []

        result: list[RelatedSymbol] = []
        seen: set[tuple[str | None, str, str]] = set()

        for child in walk(node):
            if child.type not in {'identifier', 'field_identifier'}:
                continue
            if self.symbol_index.is_declaration_node(parsed_file, child):
                continue

            definitions = self.symbol_index.resolve_reference_candidates(parsed_file, child)
            for definition in definitions:
                if exclude_id is not None and definition.symbol_id == exclude_id:
                    continue
                key = (definition.symbol_id, definition.name, definition.kind)
                if key in seen:
                    continue
                seen.add(key)
                result.append(self._related_from_definition(definition))

        return result

    def _primary_symbol(self, parsed_file: ParsedFile, node: Node | None) -> RelatedSymbol | None:
        if node is None:
            return None

        field_nodes = [child for child in walk(node) if child.type == 'field_identifier']
        if field_nodes:
            definition = self.symbol_index.resolve_reference(parsed_file, field_nodes[-1])
            if definition is not None:
                return self._related_from_definition(definition)

        for child in walk(node):
            if child.type != 'identifier':
                continue
            definition = self.symbol_index.resolve_reference(parsed_file, child)
            if definition is not None and definition.kind in SymbolIndex.VARIABLE_KINDS:
                return self._related_from_definition(definition)

        return None

    def _symbol_from_declarator(self, parsed_file: ParsedFile, declarator: Node) -> RelatedSymbol | None:
        definition = self.symbol_index.declared_symbol(parsed_file, declarator)
        return self._related_from_definition(definition) if definition is not None else None

    def _collect_control_effects(
        self,
        parsed_file: ParsedFile,
        control: Node,
        condition: Node
    ) -> list[RelatedSymbol]:
        result: list[RelatedSymbol] = []
        seen: set[str] = set()

        for child in control.named_children:
            if child.start_byte == condition.start_byte and child.end_byte == condition.end_byte:
                continue
            for node in walk(child):
                if node.type != 'call_expression':
                    continue
                function_node = node.child_by_field_name('function')
                if function_node is None:
                    continue
                if function_node.type == 'identifier':
                    for definition in self.symbol_index.resolve_reference_candidates(parsed_file, function_node):
                        if definition.symbol_id in seen:
                            continue
                        seen.add(definition.symbol_id)
                        result.append(self._related_from_definition(definition))
        return result

    def _nearest_control_with_target(self, target: Node) -> Node | None:
        current = target.parent
        while current is not None:
            if current.type in self.CONTROL_TYPES:
                condition = self._condition_node(current)
                if condition is not None and node_contains(condition, target):
                    return current
            current = current.parent
        return None

    @staticmethod
    def _condition_node(control: Node) -> Node | None:
        condition = control.child_by_field_name('condition')
        if condition is not None:
            return condition
        if control.type == 'conditional_expression':
            return control.child_by_field_name('condition')
        return None

    @staticmethod
    def _argument_index(arguments: Node, target: Node) -> int | None:
        args = [child for child in arguments.named_children]
        for index, argument in enumerate(args):
            if node_contains(argument, target):
                return index
        return None

    @staticmethod
    def _argument_at(arguments: Node, index: int) -> Node | None:
        args = [child for child in arguments.named_children]
        return args[index] if 0 <= index < len(args) else None

    @staticmethod
    def _related_from_definition(definition: SymbolDefinition) -> RelatedSymbol:
        return RelatedSymbol(
            name=definition.name,
            symbol_id=definition.symbol_id,
            kind=definition.kind,
            file=definition.file,
            line=definition.start_line
        )

    def _callee_name(self, parsed_file: ParsedFile, call: Node) -> str | None:
        function_node = call.child_by_field_name('function')
        return parsed_file.node_text(function_node) if function_node is not None else None

    @staticmethod
    def _deduplicate(records: list[DataflowRecord]) -> list[DataflowRecord]:
        result: list[DataflowRecord] = []
        seen = set()

        for record in records:
            key = (
                record.direction,
                record.operation,
                record.file,
                record.expression,
                record.callee,
                record.argument_index,
                record.destination_symbol.symbol_id if record.destination_symbol else None
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(record)

        return result
