#変更した
from __future__ import annotations

import re
from dataclasses import dataclass, field

from clang import cindex
from clang.cindex import Cursor, CursorKind


# 関連シンボル
@dataclass
class RelatedSymbol:
    name: str
    usr: str | None
    kind: str
    file: str | None
    line: int | None

# データフロー1件
@dataclass
class DataflowRecord:
    direction: str
    operation: str
    function: str | None
    file: str
    line: int
    expression: str
    operator: str | None = None
    # X = xxx の xxx
    value_expression: str | None = None
    # if等の条件式だけ
    condition_expression: str | None = None
    related_symbols: list[RelatedSymbol] = field(default_factory=list)
    # 条件によって実行が変わる処理
    effects: list[RelatedSymbol] = field(default_factory=list)
    # 関数引数
    callee: str | None = None
    argument_index: int | None = None
    destination_symbol: RelatedSymbol | None = None

class DataflowAnalyzer:

    ASSIGNMENT_OPERATORS = {"="}

    COMPOUND_ASSIGNMENT_OPERATORS = {
        "+=",
        "-=",
        "*=",
        "/=",
        "%=",
        "<<=",
        ">>=",
        "&=",
        "|=",
        "^=",
    }

    BINARY_OPERATORS = (
        ASSIGNMENT_OPERATORS
        | COMPOUND_ASSIGNMENT_OPERATORS
        | {
            "==",
            "!=",
            ">",
            "<",
            ">=",
            "<=",
            "&&",
            "||",
            "+",
            "-",
            "*",
            "/",
            "%",
            "<<",
            ">>",
            "&",
            "|",
            "^",
        }
    )

    CONTROL_KINDS = {
        CursorKind.IF_STMT,
        CursorKind.WHILE_STMT,
        CursorKind.DO_STMT,
        CursorKind.FOR_STMT,
        CursorKind.SWITCH_STMT,
        CursorKind.CONDITIONAL_OPERATOR,
    }

    C_KEYWORDS = {
        "if",
        "else",
        "for",
        "while",
        "do",
        "switch",
        "case",
        "default",
        "return",
        "sizeof",
        "int",
        "char",
        "short",
        "long",
        "float",
        "double",
        "unsigned",
        "signed",
        "const",
        "volatile",
        "static",
        "extern",
        "struct",
        "enum",
        "union",
        "void",
    }

    def __init__(self,translation_units: list[cindex.TranslationUnit]) -> None:
        self.translation_units = translation_units

    # メイン解析
    def analyze(self,target_name: str,target_usr: str) -> list[DataflowRecord]:
        result: list[DataflowRecord] = []

        for tu in self.translation_units:
            self._walk(
                cursor=tu.cursor,
                target_name=target_name,
                target_usr=target_usr,
                current_function=None,
                ancestors=[],
                result=result
            )

        return self._deduplicate(result)

    # AST走査
    def _walk(self,cursor: Cursor,target_name: str,target_usr: str,current_function: Cursor | None,ancestors: list[Cursor],result: list[DataflowRecord]) -> None:
        # 現在の関数
        if ((cursor.kind == CursorKind.FUNCTION_DECL)and(cursor.is_definition())):
            current_function = cursor

        # 対象変数の宣言
        # int g_temperature = 25;
        if ((cursor.kind == CursorKind.VAR_DECL)and(cursor.spelling == target_name)and(cursor.get_usr() == target_usr)):

            initialization = self._analyze_initialization(
                    cursor,
                    current_function,
                    target_name,
                    target_usr
                )

            if initialization is not None:
                result.append(initialization)

        # 対象変数の参照
        if self._is_target_reference(cursor,target_name,target_usr):
            records = self._analyze_reference(
                    target=cursor,
                    ancestors=ancestors,
                    current_function=current_function
                )

            result.extend(records)

        next_ancestors = ancestors + [cursor]

        for child in cursor.get_children():
            self._walk(
                cursor=child,
                target_name=target_name,
                target_usr=target_usr,
                current_function=current_function,
                ancestors=next_ancestors,
                result=result
            )

    # 初期値
    def _analyze_initialization(self,declaration: Cursor,current_function: Cursor | None,target_name: str,target_usr: str,) -> DataflowRecord | None:
        tokens = [
            token.spelling
            for token
            in declaration.get_tokens()
        ]

        if ("=" not in tokens):
            return None

        equal_index = (tokens.index("="))
        value_tokens = (tokens[equal_index + 1:])
        if ((value_tokens)and(value_tokens[-1] == ";")):
            value_tokens = (value_tokens[:-1])

        value_expression = (" ".join(value_tokens))

        file_name = (
            declaration.location.file.name
            if declaration.location.file
            else None
        )

        if file_name is None:
            return None

        function_name = (
            current_function.spelling
            if current_function
            else None
        )

        related = self._collect_symbols(declaration,exclude_usr=target_usr)
        related = self._add_unresolved_identifiers(declaration,target_name,related)

        return DataflowRecord(
            direction="into_target",
            operation="initialization",
            function=function_name,
            file=file_name,
            line=declaration.location.line,
            expression=self._source_text(declaration),
            operator="=",
            value_expression=value_expression,
            related_symbols=related
        )

    # 対象変数参照の解析
    def _analyze_reference(self,target: Cursor,ancestors: list[Cursor],current_function: Cursor | None,) -> list[DataflowRecord]:
        result: list[DataflowRecord] = []

        file_name = (
            target.location.file.name
            if target.location.file
            else None
        )

        if (file_name is None):
            return result

        function_name = (
            current_function.spelling
            if current_function
            else None
        )

        # 0. int B = X
        declaration = self._nearest(ancestors,{CursorKind.VAR_DECL})

        if (declaration is not None):
            tokens = list(declaration.get_tokens())
            equal_token = next((token for token in tokens if token.spelling == "="),None)

            if ((equal_token is not None)and(target.location.offset > equal_token.extent.end.offset)):
                destination = self._primary_symbol(declaration)

                if (destination is not None):
                    result.append(
                        DataflowRecord(
                            direction="from_target",
                            operation="initialization_source",
                            function=function_name,
                            file=file_name,
                            line=target.location.line,
                            expression=self._source_text(declaration),
                            operator="=",
                            related_symbols=[destination],
                            destination_symbol=destination
                        )
                    )

        # 1. ++ / --
        unary = self._nearest(
            ancestors,
            {
                CursorKind.UNARY_OPERATOR
            }
        )

        if (unary is not None):
            operator = self._get_unary_operator(unary)

            if (operator in {"++","--"}):
                result.append(
                    DataflowRecord(
                        direction="target_self_update",
                        operation=(
                            "increment"
                            if operator == "++"
                            else "decrement"
                        ),
                        function=function_name,
                        file=file_name,
                        line=target.location.line,
                        expression=self._source_text(unary),
                        operator=operator,
                    )
                )

                return result

        # 2. アドレス取得
        # set_value(&g_temperature)
        address_unary = None

        if unary is not None:
            unary_operator = self._get_unary_operator(unary)

            if unary_operator == "&":
                address_unary = unary

        if address_unary is not None:
            call = self._nearest(
                ancestors,
                {
                    CursorKind.CALL_EXPR
                },
            )

            # &X が関数に渡る
            if (call is not None):
                argument_index = self._argument_index(call,target)

                if (argument_index is not None):
                    callee = call.referenced
                    related = self._callee_symbol(callee)
                    related = self._add_unresolved_identifiers(call,target.spelling,related)

                    result.append(
                        DataflowRecord(
                            direction="address_to_function",
                            operation="address_argument",
                            function=function_name,
                            file=file_name,
                            line=target.location.line,
                            expression=self._source_text(call),
                            operator="&",
                            callee=(
                                callee.spelling
                                if callee
                                else call.spelling
                            ),
                            argument_index=argument_index,
                            related_symbols=related
                        )
                    )
                    # function_argument と
                    # address_taken の二重登録をしない
                    return result

            # 単純な &X
            result.append(
                DataflowRecord(
                    direction="address_escape",
                    operation="address_taken",
                    function=function_name,
                    file=file_name,
                    line=target.location.line,
                    expression=self._source_text(address_unary),
                    operator="&",
                )
            )

            return result
        # ========================================================
        # 3. 代入
        # X = Y
        # Y = X
        # X += Y
        # ========================================================
        binary = self._nearest(
            ancestors,
            {
                CursorKind.BINARY_OPERATOR,
                CursorKind.COMPOUND_ASSIGNMENT_OPERATOR
            },
        )

        if binary is not None:
            children = list(binary.get_children())

            if (len(children) >= 2):
                lhs = children[0]
                rhs = children[1]
                side = self._which_side(target,lhs,rhs)
                operator = self._get_binary_operator(binary)

                # X = RHS
                if ((side == "lhs")and(operator == "=")):
                    related = self._collect_symbols(rhs)
                    related = self._add_unresolved_identifiers(rhs,target.spelling,related)
                    result.append(
                        DataflowRecord(
                            direction="into_target",
                            operation="assignment",
                            function=function_name,
                            file=file_name,
                            line=target.location.line,
                            expression=self._source_text(binary),
                            operator=operator,
                            value_expression=self._source_text(rhs),
                            related_symbols=related
                        )
                    )
                # X += Y
                # X -= Y
                elif ((side == "lhs")and(operator in self.COMPOUND_ASSIGNMENT_OPERATORS)):
                    result.append(
                        DataflowRecord(
                            direction="target_self_update",
                            operation="compound_assignment",
                            function=function_name,
                            file=file_name,
                            line=target.location.line,
                            expression=self._source_text(binary),
                            operator=operator,
                            value_expression=self._source_text(rhs),
                            related_symbols=self._collect_symbols(rhs)
                        )
                    )

                # Y = X
                elif ((side == "rhs")and(operator in(self.ASSIGNMENT_OPERATORS | self.COMPOUND_ASSIGNMENT_OPERATORS))):
                    result.append(
                        DataflowRecord(
                            direction="from_target",
                            operation="assignment_source",
                            function=function_name,
                            file=file_name,
                            line=target.location.line,
                            expression=self._source_text(binary),
                            operator=operator,
                            related_symbols=self._collect_symbols(lhs),
                            destination_symbol=self._primary_symbol(lhs)
                        )
                    )

        # ========================================================
        # 4. 条件
        # if (X >= LIMIT)
        # ========================================================
        control = self._nearest(ancestors,self.CONTROL_KINDS)

        if (control is not None):
            condition_cursor = self._condition_containing_target(control,target)
            
            # 対象変数がif本体ではなく、
            # 本当に条件式内にある場合だけ
            if (condition_cursor is not None):
                condition_text = self._source_text(condition_cursor)
                target_usr = (
                    target.referenced.get_usr()
                    if target.referenced
                    else None
                )

                related = self._collect_symbols(condition_cursor,exclude_usr=target_usr)

                # macro等、通常AST参照にならない識別子も候補化
                related = self._add_unresolved_identifiers(condition_cursor,target.spelling,related)

                effects = self._collect_control_effects(control,condition_cursor)

                result.append(
                    DataflowRecord(
                        direction="from_target",
                        operation="condition",
                        function=function_name,
                        file=file_name,
                        line=target.location.line,
                        expression=self._source_text(control),
                        condition_expression=condition_text,
                        operator=(
                            self._get_binary_operator(condition_cursor)
                            if condition_cursor.kind
                            in {
                                CursorKind.BINARY_OPERATOR,
                                CursorKind.COMPOUND_ASSIGNMENT_OPERATOR,
                            }
                            else None
                        ),
                        related_symbols=related,
                        effects=effects,
                    )
                )

                return result

        # ========================================================
        # 5. return X
        # ========================================================
        return_stmt = self._nearest(
            ancestors,
            {
                CursorKind.RETURN_STMT
            },
        )

        if (return_stmt is not None):
            result.append(
                DataflowRecord(
                    direction="from_target",
                    operation="return",
                    function=function_name,
                    file=file_name,
                    line=target.location.line,
                    expression=self._source_text(return_stmt)
                )
            )

            return result

        # ========================================================
        # 6. foo(X)
        # ========================================================
        call = self._nearest(
            ancestors,
            {
                CursorKind.CALL_EXPR
            },
        )

        if (call is not None):
            argument_index = self._argument_index(call,target)

            if (argument_index is not None):
                callee = call.referenced

                result.append(
                    DataflowRecord(
                        direction="from_target",
                        operation="function_argument",
                        function=function_name,
                        file=file_name,
                        line=target.location.line,
                        expression=self._source_text(call),
                        callee=(
                            callee.spelling
                            if callee
                            else call.spelling
                        ),
                        argument_index=argument_index,
                        related_symbols=self._callee_symbol(callee)
                    )
                )

        return result

    # 条件式の特定
    def _condition_containing_target(self,control: Cursor,target: Cursor) -> Cursor | None:
        target_offset = target.location.offset

        for child in control.get_children():
            # { ... } は条件ではない
            if (child.kind == CursorKind.COMPOUND_STMT):
                continue

            if (child.extent.start.offset <= target_offset <= child.extent.end.offset):
                return child

        return None

    # 条件によって影響を受ける処理
    def _collect_control_effects(self,control: Cursor,condition_cursor: Cursor) -> list[RelatedSymbol]:
        result: list[RelatedSymbol] = []
        seen: set[tuple[str | None, str]] = set()

        for child in control.get_children():
            # 条件式自身は除外
            if (self._same_extent(child,condition_cursor)):
                continue

            self._collect_calls_recursive(child,result,seen)

        return result

    def _collect_calls_recursive(self,cursor: Cursor,result: list[RelatedSymbol],seen: set[tuple[str | None, str]]) -> None:
        if (cursor.kind == CursorKind.CALL_EXPR):
            referenced = cursor.referenced

            if (referenced is not None):
                usr = (referenced.get_usr() or None)
                name = (referenced.spelling or cursor.spelling)
                key = (usr,name)

                if (key not in seen):
                    seen.add(key)
                    file_name = None
                    line = None

                    if (referenced.location.file):
                        file_name = referenced.location.file.name
                        line = referenced.location.line

                    result.append(
                        RelatedSymbol(
                            name=name,
                            usr=usr,
                            kind=referenced.kind.name,
                            file=file_name,
                            line=line
                        )
                    )

        for child in cursor.get_children():
            self._collect_calls_recursive(child,result,seen)


    # 式内シンボル収集
    def _collect_symbols(self,cursor: Cursor,exclude_usr: str | None = None) -> list[RelatedSymbol]:
        result: list[RelatedSymbol] = []
        seen: set[tuple[str | None, str]] = set()

        def walk(node: Cursor) -> None:
            if (node.kind in {
                CursorKind.DECL_REF_EXPR,
                CursorKind.MEMBER_REF_EXPR,
                CursorKind.CALL_EXPR,
            }):
                referenced = (node.referenced)

                if (referenced is not None):
                    usr = (referenced.get_usr() or None)
                    if ((exclude_usr is None)or(usr != exclude_usr)):
                        name = referenced.spelling or node.spelling
                        key = (usr,name)

                        if (key not in seen):
                            seen.add(key)
                            file_name = None
                            line = None
                            if (referenced.location.file):
                                file_name = referenced.location.file.name
                                line = referenced.location.line

                            result.append(
                                RelatedSymbol(
                                    name=name,
                                    usr=usr,
                                    kind=referenced.kind.name,
                                    file=file_name,
                                    line=line
                                )
                            )

            for child in (node.get_children()):
                walk(child)

        walk(cursor)

        return result

    # macro候補など、AST参照にならない識別子
    def _add_unresolved_identifiers(self,cursor: Cursor,target_name: str,symbols: list[RelatedSymbol]) -> list[RelatedSymbol]:
        existing = {
            symbol.name
            for symbol in symbols
        }

        result = list(symbols)

        for token in cursor.get_tokens():
            text = token.spelling

            if (not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",text)):
                continue

            if (text == target_name):
                continue

            if (text in self.C_KEYWORDS):
                continue

            if (text in existing):
                continue

            existing.add(text)
            result.append(
                RelatedSymbol(
                    name=text,
                    usr=None,
                    kind="UNRESOLVED_IDENTIFIER",
                    file=None,
                    line=None
                )
            )

        return result

    def _primary_symbol(self,cursor: Cursor) -> RelatedSymbol | None:
        if (cursor.kind in {CursorKind.DECL_REF_EXPR,CursorKind.MEMBER_REF_EXPR,CursorKind.VAR_DECL,CursorKind.FIELD_DECL,CursorKind.PARM_DECL}):
            referenced = cursor.referenced

            if (referenced is not None):
                file_name = referenced.location.file.name if referenced.location.file else None

                return RelatedSymbol(
                    name=referenced.spelling,
                    usr=referenced.get_usr() or None,
                    kind=referenced.kind.name,
                    file=file_name,
                    line=referenced.location.line if referenced.location.file else None
                )

        for child in cursor.get_children():
            symbol = self._primary_symbol(child)

            if (symbol is not None):
                return symbol

        return None

    # 対象変数参照判定
    @staticmethod
    def _is_target_reference(cursor: Cursor,target_name: str,target_usr: str) -> bool:
        if (cursor.kind not in {CursorKind.DECL_REF_EXPR,CursorKind.MEMBER_REF_EXPR}):
            return False

        if (cursor.spelling != target_name):
            return False

        referenced = cursor.referenced

        if (referenced is None):
            return False

        return (referenced.get_usr() == target_usr)

    # 関数引数番号
    @staticmethod
    def _argument_index(call: Cursor,target: Cursor) -> int | None:
        try:
            arguments = list(call.get_arguments())
        except Exception:
            return None

        offset = target.location.offset

        for index, argument in enumerate(arguments):
            if (argument.extent.start.offset <= offset <= argument.extent.end.offset):
                return index

        return None

    # 左辺 / 右辺判定
    @staticmethod
    def _which_side(target: Cursor,lhs: Cursor,rhs: Cursor) -> str | None:
        offset = target.location.offset

        if (lhs.extent.start.offset <= offset <= lhs.extent.end.offset):
            return "lhs"

        if (rhs.extent.start.offset <= offset <= rhs.extent.end.offset):
            return "rhs"

        return None

    # Binary Operator取得
    def _get_binary_operator(self,cursor: Cursor) -> str | None:
        children = list(cursor.get_children())

        if (len(children) < 2):
            return None

        lhs = children[0]
        rhs = children[1]

        for token in (cursor.get_tokens()):

            offset = token.extent.start.offset

            if (lhs.extent.end.offset <= offset <= rhs.extent.start.offset):
                if (token.spelling in self.BINARY_OPERATORS):
                    return token.spelling

        return None

    # Unary Operator取得
    @staticmethod
    def _get_unary_operator(cursor: Cursor) -> str | None:
        tokens = [
            token.spelling
            for token
            in cursor.get_tokens()
        ]

        # ++ / -- を先に判定
        for operator in ("++","--","&","*","!","~","+","-"):
            if operator in tokens:
                return operator

        return None

    # 呼び出し先をRelatedSymbol化
    @staticmethod
    def _callee_symbol(cursor: Cursor | None) -> list[RelatedSymbol]:

        if (cursor is None):
            return []
        
        file_name = None
        line = None

        if (cursor.location.file):
            file_name = cursor.location.file.name
            line = cursor.location.line

        return [
            RelatedSymbol(
                name=cursor.spelling,
                usr=cursor.get_usr() or None,
                kind=cursor.kind.name,
                file=file_name,
                line=line,
            )
        ]

    # 親AST探索
    @staticmethod
    def _nearest(ancestors: list[Cursor],kinds: set,) -> Cursor | None:
        for ancestor in reversed(ancestors):
            if (ancestor.kind in kinds):
                return ancestor

        return None

    # ソース文字列
    @staticmethod
    def _source_text(cursor: Cursor) -> str:
        try:
            return " ".join(
                token.spelling
                for token
                in cursor.get_tokens()
            )

        except Exception:
            return ""

    # extent比較
    @staticmethod
    def _same_extent(a: Cursor,b: Cursor) -> bool:
        return ((a.extent.start.offset == b.extent.start.offset)and(a.extent.end.offset == b.extent.end.offset))

    # 重複除去
    @staticmethod
    def _deduplicate(records: list[DataflowRecord]) -> list[DataflowRecord]:
        result: list[DataflowRecord] = []
        seen = set()

        for record in records:
            key = (
                record.direction,
                record.operation,
                record.file,
                #record.line,
                record.expression,
                record.callee,
                record.argument_index
            )

            if (key in seen):
                continue

            seen.add(key)
            result.append(record)

        return result