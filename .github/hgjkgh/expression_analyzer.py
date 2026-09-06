from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from clang.cindex import Cursor, CursorKind

@dataclass
class ExpressionRecord:
    operation: str
    file: str
    line: int
    function: str | None
    expression: str
    operator: str | None = None
    side: str | None = None
    callee: str | None = None
    member: str | None = None

class ExpressionAnalyzer:
    """
    対象変数が式の中でどのように使用されているか解析する。
    例:
        g = x;
        x = g;
        g += 1;
        g++;
        if (g >= LIMIT)
        foo(g);
        foo(&g);
        return g;
        data.member
    """
    ASSIGNMENT_OPERATORS = {
        "="
    }

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
        "^="
    }

    COMPARISON_OPERATORS = {
        "==",
        "!=",
        ">",
        "<",
        ">=",
        "<="
    }

    LOGICAL_OPERATORS = {
        "&&",
        "||"
    }

    CONTROL_STATEMENTS = {
        CursorKind.IF_STMT,
        CursorKind.WHILE_STMT,
        CursorKind.DO_STMT,
        CursorKind.FOR_STMT,
        CursorKind.SWITCH_STMT,
        CursorKind.CONDITIONAL_OPERATOR
    }

    def analyze(self,translation_units,target_name: str,target_usr: str,) -> list[ExpressionRecord]:
        results: list[ExpressionRecord] = []

        for tu in translation_units:
            self._walk(
                cursor=tu.cursor,
                target_name=target_name,
                target_usr=target_usr,
                current_function=None,
                ancestors=[],
                results=results
            )

        return self._remove_duplicates(results)

    # AST走査
    def _walk(self,cursor: Cursor,target_name: str,target_usr: str,current_function: Cursor | None,ancestors: list[Cursor],results: list[ExpressionRecord]) -> None:
        if ((cursor.kind == CursorKind.FUNCTION_DECL)and(cursor.is_definition())):
            current_function = cursor

        if (self._is_target_reference(cursor,target_name,target_usr)):
            record = self._classify_reference(
                cursor=cursor,
                ancestors=ancestors,
                current_function=current_function
            )

            if (record is not None):
                results.append(record)

        new_ancestors = ancestors + [cursor]

        for child in cursor.get_children():
            self._walk(
                cursor=child,
                target_name=target_name,
                target_usr=target_usr,
                current_function=current_function,
                ancestors=new_ancestors,
                results=results
            )

    # 対象変数判定
    def _is_target_reference(self,cursor: Cursor,target_name: str,target_usr: str) -> bool:
        if (cursor.kind not in {CursorKind.DECL_REF_EXPR,CursorKind.MEMBER_REF_EXPR}):
            return False

        if (cursor.spelling != target_name):
            return False

        referenced = cursor.referenced

        if (referenced is None):
            return False

        usr = referenced.get_usr()

        return usr == target_usr

    # 使用方法の分類
    def _classify_reference(self,cursor: Cursor,ancestors: list[Cursor],current_function: Cursor | None) -> ExpressionRecord | None:
        file_name = (
            cursor.location.file.name
            if cursor.location.file
            else None
        )

        if (file_name is None):
            return None

        function_name = (
            current_function.spelling
            if current_function is not None
            else None
        )

        # --------------------------------------------------------
        # 1. アドレス取得
        # &g
        # foo(&g)
        # --------------------------------------------------------
        unary = self._nearest_ancestor(
            ancestors,
            {
                CursorKind.UNARY_OPERATOR,
            },
        )

        if unary is not None:
            operator = self._get_unary_operator(unary)

            if operator == "&":
                call = self._nearest_ancestor(
                    ancestors,
                    {
                        CursorKind.CALL_EXPR,
                    },
                )

                if call is not None:
                    return ExpressionRecord(
                        operation="address_argument",
                        file=file_name,
                        line=cursor.location.line,
                        function=function_name,
                        expression=self._source_text(call),
                        operator="&",
                        callee=self._get_callee(call)
                    )

                return ExpressionRecord(
                    operation="address_taken",
                    file=file_name,
                    line=cursor.location.line,
                    function=function_name,
                    expression=self._source_text(unary),
                    operator="&"
                )

            # ----------------------------------------------------
            # ++g
            # g++
            # --g
            # g--
            # ----------------------------------------------------
            if (operator in {"++","--"}):
                return ExpressionRecord(
                    operation="read_write",
                    file=file_name,
                    line=cursor.location.line,
                    function=function_name,
                    expression=self._source_text(unary),
                    operator=operator,
                    side="lhs"
                )

        # --------------------------------------------------------
        # 2. 代入
        # g = xxx
        # xxx = g
        # --------------------------------------------------------
        binary = self._nearest_ancestor(
            ancestors,
            {
                CursorKind.BINARY_OPERATOR,
                CursorKind.COMPOUND_ASSIGNMENT_OPERATOR,
            },
        )

        if binary is not None:
            operator = self._get_binary_operator(binary)
            side = self._get_operand_side(binary,cursor)

            if operator in self.ASSIGNMENT_OPERATORS:
                if side == "lhs":
                    return ExpressionRecord(
                        operation="write",
                        file=file_name,
                        line=cursor.location.line,
                        function=function_name,
                        expression=self._source_text(binary),
                        operator=operator,
                        side="lhs"
                    )

                return ExpressionRecord(
                    operation="read",
                    file=file_name,
                    line=cursor.location.line,
                    function=function_name,
                    expression=self._source_text(binary),
                    operator=operator,
                    side="rhs"
                )

            # ----------------------------------------------------
            # g += 1
            # g -= 1
            # ----------------------------------------------------
            if (operator in self.COMPOUND_ASSIGNMENT_OPERATORS):
                if side == "lhs":
                    return ExpressionRecord(
                        operation="read_write",
                        file=file_name,
                        line=cursor.location.line,
                        function=function_name,
                        expression=self._source_text(binary),
                        operator=operator,
                        side="lhs"
                    )

                return ExpressionRecord(
                    operation="read",
                    file=file_name,
                    line=cursor.location.line,
                    function=function_name,
                    expression=self._source_text(binary),
                    operator=operator,
                    side="rhs"
                )

        # --------------------------------------------------------
        # 3. 条件
        # if (g >= LIMIT)
        # while (g)
        # --------------------------------------------------------
        control = self._nearest_ancestor(ancestors,self.CONTROL_STATEMENTS)

        if control is not None:
            operator = None

            if binary is not None:
                operator = self._get_binary_operator(binary)

            return ExpressionRecord(
                operation="condition_read",
                file=file_name,
                line=cursor.location.line,
                function=function_name,
                expression=self._source_text(control),
                operator=operator
            )

        # --------------------------------------------------------
        # 4. return
        # return g;
        # --------------------------------------------------------
        return_stmt = self._nearest_ancestor(
            ancestors,
            {
                CursorKind.RETURN_STMT,
            },
        )

        if return_stmt is not None:
            return ExpressionRecord(
                operation="return_read",
                file=file_name,
                line=cursor.location.line,
                function=function_name,
                expression=self._source_text(return_stmt)
            )

        # --------------------------------------------------------
        # 5. 関数引数
        # foo(g)
        # --------------------------------------------------------
        call = self._nearest_ancestor(
            ancestors,
            {
                CursorKind.CALL_EXPR,
            },
        )

        if call is not None:
            return ExpressionRecord(
                operation="argument_read",
                file=file_name,
                line=cursor.location.line,
                function=function_name,
                expression=self._source_text(call),
                callee=self._get_callee(call)
            )

        # --------------------------------------------------------
        # 6. メンバアクセス
        # target.member
        # target->member
        # --------------------------------------------------------
        member = self._nearest_ancestor(
            ancestors,
            {
                CursorKind.MEMBER_REF_EXPR,
            },
        )

        if ((member is not None)and(member != cursor)):
            return ExpressionRecord(
                operation="member_access",
                file=file_name,
                line=cursor.location.line,
                function=function_name,
                expression=self._source_text(member),
                member=member.spelling
            )

        # --------------------------------------------------------
        # 7. 配列アクセス
        # target[i]
        # --------------------------------------------------------
        array = self._nearest_ancestor(
            ancestors,
            {
                CursorKind.ARRAY_SUBSCRIPT_EXPR,
            },
        )

        if array is not None:
            return ExpressionRecord(
                operation="array_access",
                file=file_name,
                line=cursor.location.line,
                function=function_name,
                expression=self._source_text(array)
            )
        # --------------------------------------------------------
        # 8. その他
        # --------------------------------------------------------
        return ExpressionRecord(
            operation="read",
            file=file_name,
            line=cursor.location.line,
            function=function_name,
            expression=self._source_text(cursor)
        )

    # 親AST探索

    @staticmethod
    def _nearest_ancestor(ancestors: list[Cursor],kinds: set) -> Cursor | None:
        for ancestor in reversed(ancestors):
            if ancestor.kind in kinds:
                return ancestor

        return None

    # Binary Operator
    def _get_binary_operator(self,cursor: Cursor) -> str | None:
        children = list(cursor.get_children())

        if (len(children) < 2):
            return self._operator_from_tokens(cursor)

        lhs = children[0]
        rhs = children[1]

        try:
            lhs_end = lhs.extent.end.offset
            rhs_start = rhs.extent.start.offset

            for token in cursor.get_tokens():
                offset = token.extent.start.offset

                if (lhs_end <= offset <= rhs_start):
                    if (
                        token.spelling
                        in
                        self.ASSIGNMENT_OPERATORS
                        | self.COMPOUND_ASSIGNMENT_OPERATORS
                        | self.COMPARISON_OPERATORS
                        | self.LOGICAL_OPERATORS
                        | {
                            "+",
                            "-",
                            "*",
                            "/",
                            "%",
                            "<<",
                            ">>",
                            "&",
                            "|",
                            "^"
                        }
                    ):
                        return token.spelling

        except Exception:
            pass

        return self._operator_from_tokens(cursor)

    def _operator_from_tokens(self,cursor: Cursor) -> str | None:

        known = (
            self.COMPOUND_ASSIGNMENT_OPERATORS
            | self.COMPARISON_OPERATORS
            | self.LOGICAL_OPERATORS
            | self.ASSIGNMENT_OPERATORS
            | {
                "+",
                "-",
                "*",
                "/",
                "%",
                "<<",
                ">>",
                "&",
                "|",
                "^"
            }
        )

        tokens = [
            token.spelling
            for token in cursor.get_tokens()
        ]

        # += などを = より先に検索
        for operator in sorted(known,key=len,reverse=True):
            if operator in tokens:
                return operator

        return None

    # Unary Operator
    @staticmethod
    def _get_unary_operator(cursor: Cursor) -> str | None:
        tokens = [
            token.spelling
            for token in cursor.get_tokens()
        ]

        for token in tokens:
            if token in {
                "&",
                "*",
                "++",
                "--",
                "+",
                "-",
                "!",
                "~"
            }:
                return token

        return None

    # 左辺 / 右辺
    @staticmethod
    def _get_operand_side(binary: Cursor,target: Cursor) -> str | None:
        children = list(binary.get_children())

        if (len(children) < 2):
            return None

        lhs = children[0]
        rhs = children[1]

        target_offset = target.location.offset

        if (lhs.extent.start.offset <= target_offset <= lhs.extent.end.offset):
            return "lhs"

        if (rhs.extent.start.offset <= target_offset <= rhs.extent.end.offset):
            return "rhs"

        return None

    # 呼び出し関数
    @staticmethod
    def _get_callee(call: Cursor) -> str | None:
        referenced = call.referenced

        if referenced is not None:
            return referenced.spelling

        if call.spelling:
            return call.spelling

        return None

    # ソース取得
    @staticmethod
    def _source_text(cursor: Cursor) -> str:

        try:
            tokens = [
                token.spelling
                for token in cursor.get_tokens()
            ]

            return " ".join(tokens)

        except Exception:
            return ""

    # 重複削除
    @staticmethod
    def _remove_duplicates(records: list[ExpressionRecord],) -> list[ExpressionRecord]:
        result: list[ExpressionRecord] = []
        seen = set()

        for record in records:
            key = (
                record.operation,
                record.file,
                record.line,
                record.function,
                record.expression
            )

            if key in seen:
                continue

            seen.add(key)
            result.append(record)

        return result