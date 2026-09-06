from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class ProjectFiles:
    root: Path
    c_files: tuple[Path, ...]
    h_files: tuple[Path, ...]

class ProjectScanner:
    """Cプロジェクト配下の .c / .h ファイルを探索する。"""
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def scan(self) -> ProjectFiles:
        self._validate_root()

        c_files = tuple(
            sorted(
                path
                for path in self.project_root.rglob("*")
                if path.is_file() and path.suffix.lower() == ".c"
            )
        )

        h_files = tuple(
            sorted(
                path
                for path in self.project_root.rglob("*")
                if path.is_file() and path.suffix.lower() == ".h"
            )
        )

        return ProjectFiles(root=self.project_root,c_files=c_files,h_files=h_files)

    def _validate_root(self) -> None:
        if (not self.project_root.exists()):
            raise FileNotFoundError(f"フォルダが存在しません: {self.project_root}")
        if (not self.project_root.is_dir()):
            raise NotADirectoryError(f"フォルダではありません: {self.project_root}")