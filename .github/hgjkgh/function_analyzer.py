from __future__ import annotations

from dataclasses import dataclass, field

from clang import cindex
from clang.cindex import Cursor, CursorKind


@dataclass
class FunctionInfo:
    name: str
    usr: str

    file: str
    line: int
    end_line: int

    calls: set[str] = field(
        default_factory=set
    )


class FunctionAnalyzer:

    def __init__(self,translation_units: list[cindex.TranslationUnit]) -> None:

        self.translation_units = translation_units
        self.functions: dict[str,FunctionInfo] = {}

    # 全関数を解析
    def analyze(self) -> dict[str, FunctionInfo]:
        for tu in self.translation_units:
            self._walk(tu.cursor,current_function=None)

        return self.functions

    # AST走査
    def _walk(self,cursor: Cursor,current_function: Cursor | None) -> None:
        # 関数定義
        if ((cursor.kind == CursorKind.FUNCTION_DECL)and(cursor.is_definition())):
            current_function = cursor
            usr = cursor.get_usr()

            if ((usr)and(cursor.location.file)):
                self.functions.setdefault(
                    usr,
                    FunctionInfo(
                        name=cursor.spelling,
                        usr=usr,
                        file=cursor.location.file.name,
                        line=cursor.extent.start.line,
                        end_line=cursor.extent.end.line
                    ),
                )

        # 関数呼び出し
        if((cursor.kind == CursorKind.CALL_EXPR)and(current_function is not None)):
            caller_usr = current_function.get_usr()
            referenced = cursor.referenced

            if (referenced is not None):
                callee_usr = referenced.get_usr()

                if ((caller_usr)and(callee_usr)and(caller_usr in self.functions)):
                    self.functions[caller_usr].calls.add(callee_usr)

        for child in cursor.get_children():
            self._walk(child,current_function)


    # USRから関数取得
    def get(self,usr: str) -> FunctionInfo | None:
        return self.functions.get(usr)


    # 名前検索
    def find_by_name(self,name: str) -> list[FunctionInfo]:
        return [
            function
            for function
            in self.functions.values()
            if function.name == name
        ]