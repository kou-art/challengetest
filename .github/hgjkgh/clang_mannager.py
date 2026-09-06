from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from clang import cindex


class ClangManager:
    #libclangの初期化とClang Indexの生成を担当する。

    def __init__(self, libclang_path: str | None = None) -> None:
        self.libclang_path = libclang_path
        self._index: cindex.Index | None = None

    def initialize(self) -> None:
        if self._index is not None:
            return

        path = self._find_libclang()
        # Index.create() より前に設定する
        cindex.Config.set_library_file(path)

        self._index = cindex.Index.create()

    def get_index(self) -> cindex.Index:
        if self._index is None:
            raise RuntimeError("ClangManager.initialize() を先に実行してください。")

        return self._index

    def _find_libclang(self) -> str:
        # 1. 明示指定
        if self.libclang_path:
            path = Path(self.libclang_path)

            if not path.is_file():
                raise FileNotFoundError(f"libclangが存在しません: {path}")

            return str(path.resolve())

        # 2. 環境変数
        env_path = os.getenv("LIBCLANG_PATH")

        if env_path:
            path = Path(env_path)

            if not path.is_file():
                raise FileNotFoundError(f"LIBCLANG_PATHが不正です: {path}")

            return str(path.resolve())

        # 3. pip install libclang の配置先を探す
        spec = importlib.util.find_spec("clang")

        if spec is None or spec.origin is None:
            raise RuntimeError(
                "clang Python packageがありません。\n"
                "pip install libclang を実行してください。"
            )

        clang_dir = Path(spec.origin).parent

        candidates: list[Path] = []

        candidates.extend(clang_dir.rglob("libclang.so"))
        candidates.extend(clang_dir.rglob("libclang.so.*"))
        candidates.extend(clang_dir.rglob("libclang.dll"))
        candidates.extend(clang_dir.rglob("libclang.dylib"))

        candidates = sorted(
            {
                path.resolve()
                for path in candidates
                if path.is_file()
            }
        )

        if not candidates:
            raise RuntimeError(
                "libclang本体が見つかりません。\n"
                "LIBCLANG_PATHを設定してください。"
            )

        return str(candidates[0])