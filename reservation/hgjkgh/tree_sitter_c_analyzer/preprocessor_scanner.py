from __future__ import annotations

import re
from dataclasses import dataclass

from parsed_file import ParsedFile


@dataclass
class MacroDefinition:
    name: str
    file: str
    start_line: int
    end_line: int
    text: str


@dataclass
class PreprocessorDirective:
    kind: str
    file: str
    start_line: int
    end_line: int
    text: str


class PreprocessorScanner:
    MACRO_RE = re.compile(r'^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)')
    DIRECTIVE_RE = re.compile(r'^\s*#\s*(define|include|if|ifdef|ifndef|elif|else|endif|pragma|undef|error|warning)\b')

    def scan(self, parsed_file: ParsedFile) -> tuple[list[MacroDefinition], list[PreprocessorDirective]]:
        lines = parsed_file.text.splitlines()
        macros: list[MacroDefinition] = []
        directives: list[PreprocessorDirective] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            directive_match = self.DIRECTIVE_RE.match(line)

            if directive_match is None:
                index += 1
                continue

            start = index
            parts = [line]
            while parts[-1].rstrip().endswith('\\') and index + 1 < len(lines):
                index += 1
                parts.append(lines[index])

            text = '\n'.join(parts)
            kind = directive_match.group(1)
            directives.append(
                PreprocessorDirective(
                    kind=kind,
                    file=str(parsed_file.path),
                    start_line=start + 1,
                    end_line=index + 1,
                    text=text
                )
            )

            macro_match = self.MACRO_RE.match(line)
            if macro_match is not None:
                macros.append(
                    MacroDefinition(
                        name=macro_match.group(1),
                        file=str(parsed_file.path),
                        start_line=start + 1,
                        end_line=index + 1,
                        text=text
                    )
                )

            index += 1

        return macros, directives
