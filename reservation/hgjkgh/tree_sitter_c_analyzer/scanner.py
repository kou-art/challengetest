from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProjectFiles:
    root: Path
    c_files: list[Path]
    h_files: list[Path]

    @property
    def all_files(self) -> list[Path]:
        return self.c_files + self.h_files


class ProjectScanner:
    def scan(self, root: Path) -> ProjectFiles:
        root = root.resolve()
        c_files = sorted(path for path in root.rglob('*.c') if path.is_file())
        h_files = sorted(path for path in root.rglob('*.h') if path.is_file())
        return ProjectFiles(root=root, c_files=c_files, h_files=h_files)
