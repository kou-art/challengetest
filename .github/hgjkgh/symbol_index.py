from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from clang import cindex
from clang.cindex import Cursor, CursorKind

# シンボル定義
@dataclass
class SymbolDefinition:
    name: str
    usr: str | None
    kind: str
    file: str
    start_line: int
    end_line: int
    type_name: str | None = None
    is_definition: bool = False

    # このシンボルを理解するために必要な型
    related_type_usrs: set[str] = field(default_factory=set)

# SymbolIndex
class SymbolIndex:
    INDEX_KINDS = {
        CursorKind.FUNCTION_DECL,
        CursorKind.VAR_DECL,
        CursorKind.FIELD_DECL,
        CursorKind.STRUCT_DECL,
        CursorKind.UNION_DECL,
        CursorKind.ENUM_DECL,
        CursorKind.ENUM_CONSTANT_DECL,
        CursorKind.TYPEDEF_DECL,
        CursorKind.MACRO_DEFINITION
    }

    def __init__(self,translation_units: list[cindex.TranslationUnit],project_root: Path) -> None:
        self.translation_units = translation_units
        self.project_root = project_root.resolve()
        # USR → 定義一覧
        self.by_usr: dict[str,list[SymbolDefinition]] = {}
        # 名前 → 定義一覧
        self.by_name: dict[str,list[SymbolDefinition]] = {}
        self._seen: set[tuple] = set()

    # 構築
    def build(self) -> None:
        for tu in self.translation_units:
            self._walk(tu.cursor)

    # AST走査
    def _walk(self,cursor: Cursor) -> None:
        if (cursor.kind in self.INDEX_KINDS):
            self._register(cursor)

        for child in (cursor.get_children()):
            self._walk(child)

    # 登録
    def _register(self,cursor: Cursor) -> None:
        if (cursor.location.file is None):
            return

        file_path = Path(cursor.location.file.name).resolve()

        # Windows SDK / 標準ライブラリ等を除外
        # プロジェクト内部だけ索引化する
        if (not self._inside_project(file_path)):
            return

        name = cursor.spelling
        if (not name):
            return

        usr = cursor.get_usr() or None
        kind = cursor.kind.name
        start_line = cursor.extent.start.line
        end_line = cursor.extent.end.line

        if (end_line < start_line):
            end_line = start_line

        # 型
        type_name = None

        try:
            if (cursor.kind in {CursorKind.VAR_DECL,CursorKind.FIELD_DECL,CursorKind.FUNCTION_DECL,CursorKind.TYPEDEF_DECL}):
                type_name = cursor.type.spelling or None
        except Exception:
            pass

        # 定義
        is_definition = self._is_definition(cursor)

        # 関連型
        related_types = self._collect_related_types(cursor)
        definition = SymbolDefinition(
                name=name,
                usr=usr,
                kind=kind,
                file=str(file_path),
                start_line=start_line,
                end_line=end_line,
                type_name=type_name,
                is_definition=is_definition,
                related_type_usrs=related_types
            )

        # 同じ.hが複数TUから出てくるため重複除去
        key = (name,kind,str(file_path),start_line,end_line)

        if (key in self._seen):
            return

        self._seen.add(key)

        # 名前索引
        self.by_name.setdefault(name,[]).append(definition)

        # USR索引
        if (usr):
            self.by_usr.setdefault(usr,[]).append(definition)

    # プロジェクト内部判定
    def _inside_project(self,file_path: Path) -> bool:
        try:
            file_path.relative_to(self.project_root)
            return True
        except ValueError:
            return False

    # 定義判定
    @staticmethod
    def _is_definition(cursor: Cursor) -> bool:
        if (cursor.kind in {CursorKind.FUNCTION_DECL,CursorKind.VAR_DECL}):
            try:
                return (cursor.is_definition())
            except Exception:
                return False

        # struct/enum/typedef/macro等
        return True

    # 関連型を取得
    def _collect_related_types(self,cursor: Cursor) -> set[str]:
        result: set[str] = set()

        # 変数 / field
        if (cursor.kind in {CursorKind.VAR_DECL,CursorKind.FIELD_DECL}):
            self._add_type_usr(cursor.type,result)
        # 関数
        # 戻り値 + 引数型
        elif (cursor.kind == CursorKind.FUNCTION_DECL):
            try:
                self._add_type_usr(cursor.result_type,result)
            except Exception:
                pass

            try:
                for argument in (cursor.get_arguments()):
                    self._add_type_usr(argument.type,result)
            except Exception:
                pass
        # typedef
        elif (cursor.kind == CursorKind.TYPEDEF_DECL):
            try:
                self._add_type_usr(cursor.underlying_typedef_type,result)
            except Exception:
                pass
        # struct / union のfield型
        elif (cursor.kind in {CursorKind.STRUCT_DECL,CursorKind.UNION_DECL}):
            for child in (cursor.get_children()):
                if (child.kind == CursorKind.FIELD_DECL):
                    self._add_type_usr(child.type,result)

        return result

    # Type → USR
    @staticmethod
    def _add_type_usr(clang_type,result: set[str]) -> None:
        try:
            declaration = clang_type.get_declaration()

            if (declaration is None):
                return

            usr = declaration.get_usr() or None

            if (usr):
                result.add(usr)
        except Exception:
            pass

    # USR検索
    def find_by_usr(self,usr: str) -> list[SymbolDefinition]:
        return list(self.by_usr.get(usr,[]))

    # 名前検索
    def find_by_name(self,name: str) -> list[SymbolDefinition]:
        return list(self.by_name.get(name,[]))