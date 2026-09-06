from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from code_extractor import CodeBlock

@dataclass
class ContextBuildResult:
    text: str
    estimated_tokens: int
    included_blocks: int
    excluded_blocks: int

class ContextBuilder:
    def __init__(self,max_tokens: int = 90000,) -> None:
        self.max_tokens = max_tokens

    # ============================================================
    # トークン概算
    # Cコード + 日本語を考慮し、
    # 安全側に 2文字 ≒ 1token とする
    # 128Kモデルへ90K程度まで入れるなら、
    # 回答・プロンプト用の余裕も残る
    # ============================================================
    @staticmethod
    def estimate_tokens(text: str,) -> int:

        return max(1,math.ceil(len(text) / 2))

    # Context構築
    def build(self,candidate,blocks: list[CodeBlock]) -> ContextBuildResult:
        parts: list[str] = []

        # ヘッダ
        header = (
            "============================================================\n"
            "TARGET VARIABLE\n"
            "============================================================\n"
            f"{candidate.name}\n"
            "\n"
        )
        parts.append(header)

        current_tokens = self.estimate_tokens(header)

        # 対象変数の事実
        summary_lines = [
            "============================================================",
            "ANALYSIS FACTS",
            "============================================================",
            "",
            "Direct functions:",
        ]

        for function in sorted(candidate.functions):
            summary_lines.append(f"- {function}")

        summary_lines.extend(["","Data flow:"])

        for flow in (candidate.dataflow):
            line = (
                f"- "
                f"{flow.direction}"
                f" / "
                f"{flow.operation}"
                f" / "
                f"{flow.expression}"
            )

            if (flow.value_expression):
                line += (
                    f" / value="
                    f"{flow.value_expression}"
                )

            if (flow.condition_expression):
                line += (
                    f" / condition="
                    f"{flow.condition_expression}"
                )

            if flow.callee:
                line += (
                    f" / callee="
                    f"{flow.callee}"
                )

            summary_lines.append(line)

        summary = (
            "\n".join(
                summary_lines
            )
            + "\n\n"
        )

        summary_tokens = self.estimate_tokens(summary)

        if ((current_tokens + summary_tokens) <= self.max_tokens):
            parts.append(summary)

            current_tokens += (summary_tokens)

        # 実Cコード
        code_header = (
            "============================================================\n"
            "RELATED SOURCE CODE\n"
            "============================================================\n"
            "\n"
        )

        header_tokens = self.estimate_tokens(code_header)

        if ((current_tokens + header_tokens) <= self.max_tokens):
            parts.append(code_header)
            current_tokens += header_tokens
            
        included = 0
        excluded = 0

        # 高スコア順
        blocks = sorted(
            blocks,
            key=lambda block: (
                -block.score,
                block.file,
                block.start_line
            )
        )

        for block in blocks:
            block_text = (
                f"----- FILE: {block.file}\n"
                f"----- LINES: "
                f"{block.start_line}"
                f"-"
                f"{block.end_line}\n"
                f"----- PRIORITY: "
                f"{block.score}\n"
                f"----- REASON: "
                f"{block.reason}\n"
                "\n"
                f"{block.code}\n"
                "\n"
            )

            tokens = self.estimate_tokens(block_text)

            if ((current_tokens + tokens) > self.max_tokens):
                excluded += 1
                continue

            parts.append(block_text)

            current_tokens += tokens

            included += 1

        text = "".join(parts)

        return ContextBuildResult(
            text=text,
            estimated_tokens=current_tokens,
            included_blocks=included,
            excluded_blocks=excluded
        )

    # ファイル保存
    @staticmethod
    def save(result: ContextBuildResult,output_file: Path) -> None:
        output_file.parent.mkdir(parents=True,exist_ok=True)

        output_file.write_text(result.text,encoding="utf-8")