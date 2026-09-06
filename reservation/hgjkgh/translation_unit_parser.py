from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path

from clang import cindex

@dataclass
class ParseResult:
    translation_units: list[cindex.TranslationUnit]
    failed_files: list[Path]

class TranslationUnitParser:
    #.cファイルをClang TranslationUnitとして解析する.
    def __init__(self,index: cindex.Index,project_root: Path,c_files: tuple[Path, ...],h_files: tuple[Path, ...]) -> None:
        self.index = index
        self.project_root = project_root.resolve()
        self.c_files = c_files
        self.h_files = h_files
        self.compile_commands = self._load_compile_commands()
        self.fallback_include_dirs = sorted(
            {
                path.parent.resolve()
                for path in (*c_files, *h_files)
            }
        )

    def parse_all(self) -> ParseResult:
        translation_units: list[cindex.TranslationUnit] = []
        failed_files: list[Path] = []

        for c_file in self.c_files:
            print(f"[Clang] {c_file}")

            try:
                args = self._get_clang_args(c_file)
                tu = self.index.parse(
                    str(c_file),
                    args=args,
                    options=cindex.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
                )

                diagnostics = list(tu.diagnostics)

                # Diagnostic表示
                for diagnostic in diagnostics:
                    if (diagnostic.severity == cindex.Diagnostic.Warning):
                        level = "WARNING"
                    elif (diagnostic.severity == cindex.Diagnostic.Error):
                        level = "ERROR"
                    elif (diagnostic.severity == cindex.Diagnostic.Fatal):
                        level = "FATAL"
                    else:
                        level = "INFO"

                    print(
                        f"  [{level}] "
                        f"{diagnostic}"
                    )

                # Fatalだけ解析失敗扱い

                fatal_errors = [
                    diagnostic
                    for diagnostic in diagnostics
                    if diagnostic.severity
                    >= cindex.Diagnostic.Fatal
                ]

                if fatal_errors:
                    print("  → AST解析継続不可")
                    failed_files.append(c_file)
                    continue

                # ErrorがあってもASTが生成されていれば使う
                translation_units.append(tu)

                if diagnostics:
                    print(
                        "  → AST取得成功 "
                        "(diagnosticあり)"
                    )
                else:
                    print("  → AST取得成功")

            except Exception as exc:
                print(f"  [EXCEPTION] {exc}")

                failed_files.append(c_file)

        return ParseResult(translation_units=translation_units,failed_files=failed_files)

    # compile_commands.json
    def _load_compile_commands(self) -> dict[Path, dict]:
        path = self.project_root / "compile_commands.json"

        if not path.exists():
            print(
                "compile_commands.json: なし "
                "→ fallback include pathを使用"
            )
            return {}

        print(f"compile_commands.json: 使用 {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        commands: dict[Path, dict] = {}

        for item in data:
            directory = Path(item.get("directory",self.project_root))

            source = Path(item["file"])

            if (not source.is_absolute()):
                source = directory / source

            commands[source.resolve()] = item

        return commands

    # .cごとのClang引数
    def _get_clang_args(self,c_file: Path) -> list[str]:
        command = self.compile_commands.get(c_file.resolve())

        if (command):
            return self._args_from_compile_command(command,c_file)

        return self._fallback_args()

    def _fallback_args(self) -> list[str]:
        args = ["-x","c","-std=c11"]

        for directory in self.fallback_include_dirs:
            args.append(f"-I{directory}")

        return args

    # compile_commands.jsonのコマンドを解析
    def _args_from_compile_command(self,command: dict,c_file: Path) -> list[str]:
        if ("arguments" in command):
            args = list(command["arguments"])
        else:
            args = shlex.split(command["command"])

        if (not args):
            return self._fallback_args()

        # gcc / clang などの実行ファイルを除去
        args = args[1:]
        result: list[str] = []
        skip_next = False

        for arg in args:
            if (skip_next):
                skip_next = False
                continue
            # コンパイルのみ
            if (arg == "-c"):
                continue
            # 出力ファイル
            if (arg == "-o"):
                skip_next = True
                continue
            if (arg.startswith("-o")):
                continue

            # 入力.c自身
            try:
                if (Path(arg).resolve() == c_file.resolve()):
                    continue
            except Exception:
                pass

            result.append(arg)

        return result