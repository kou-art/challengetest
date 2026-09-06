from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class CodeBlock:
    file: str
    start_line: int
    end_line: int
    score: int
    reason: str
    code: str


class CodeExtractor:
    """
    関連定義の実ソースコードを取得する。

    以下を含める:
    ・対象定義本体
    ・対象定義の直前に連続している // コメント
    ・対象定義の直前にある /* ... */ コメント
    ・関数内部コメント
    ・同一行末尾コメント
    """

    def __init__(self,max_leading_comment_lines: int = 50,) -> None:

        self.max_leading_comment_lines = max_leading_comment_lines

    # 関連コード抽出
    def extract(self,ranked_definitions,) -> list[CodeBlock]:

        blocks: list[CodeBlock] = []
        seen: set[tuple] = set()

        for ranked in (ranked_definitions):

            definition = (ranked.definition)
            # ソース取得 直前コメントも含める
            extracted = self._read_source_with_comments(
                    file_name=definition.file,
                    start_line=definition.start_line,
                    end_line=definition.end_line
                )
            
            if extracted is None:
                continue

            actual_start_line, code = (extracted)

            if not code.strip():
                continue

            # コメントを含めた範囲で重複判定
            key = (definition.file,actual_start_line,definition.end_line)

            if key in seen:
                continue

            seen.add(key)

            blocks.append(
                CodeBlock(
                    file=definition.file,
                    start_line=actual_start_line,
                    end_line=definition.end_line,
                    score=ranked.score,
                    reason=ranked.reason,
                    code=code
                )
            )

        # 同じコード範囲の包含関係を整理
        return self._remove_contained(blocks)

    # ソース + 直前コメント取得
    def _read_source_with_comments(self,file_name: str,start_line: int,end_line: int,) -> tuple[int, str] | None:

        path = Path(file_name)

        try:
            lines = path.read_text(encoding="utf-8",errors="replace",).splitlines()

        except OSError:
            return None

        if not lines:
            return None

        # 元の定義範囲
        start_line = max(1,start_line)
        end_line = min(len(lines),end_line)

        if start_line > end_line:
            return None

        # 直前コメントを探す
        comment_start_line = self._find_leading_comment_start(
                lines=lines,
                definition_start_line=start_line,
            )
        

        actual_start_line = (
            comment_start_line
            if comment_start_line
            is not None
            else start_line
        )

        # コード取得
        selected = lines[actual_start_line - 1:end_line]

        code = "\n".join(selected)

        return (actual_start_line,code)

    # 定義直前のコメント開始行を探す
    def _find_leading_comment_start(self,lines: list[str],definition_start_line: int,) -> int | None:
        """
        定義の直前にあるコメントだけを取得する。
        対応:
            // comment

            /// Doxygen
            //! Doxygen

            /*
             * comment
             */

            /**
             * Doxygen
             */

            /*!
             * Doxygen
             */

        コメントと定義の間に空行がある場合は取得しない。
        関係の薄いコメントを拾い過ぎないため。
        """

        # definition_start_line は1始まり
        index = (definition_start_line - 2)

        if index < 0:
            return None

        line = (lines[index].strip())

        # 空行なら終了
        if not line:
            return None

        # --------------------------------------------------------
        # //
        #
        # 例:
        #
        # // 現在温度
        # // センサから更新
        # int g_temperature;
        # --------------------------------------------------------
        if line.startswith("//"):

            first_index = index
            count = 1
            index -= 1

            while ((index >= 0)and(count < self.max_leading_comment_lines)):
                current = lines[index].strip()

                if current.startswith("//"):
                    first_index = index
                    count += 1
                    index -= 1
                else:
                    break

            return (first_index + 1)

        # --------------------------------------------------------
        # /* ... */
        #
        # 定義直前の行が */ なら
        # 上方向へ /* を探す
        # --------------------------------------------------------
        if line.endswith("*/"):
            first_index = index
            count = 1
            # 1行コメント
            # /* temperature */
            # int g_temperature;
            if "/*" in line:
                return (index + 1)

            index -= 1

            while ((index >= 0)and(count < self.max_leading_comment_lines)):
                current = lines[index].strip()

                first_index = index
                count += 1

                if "/*" in current:
                    return (first_index + 1)

                index -= 1

            # /* が見つからない場合は
            # 壊れたコメントとして採用しない
            return None

        return None

    # 範囲包含による重複除去
    @staticmethod
    def _remove_contained(blocks: list[CodeBlock]) -> list[CodeBlock]:
        result: list[CodeBlock] = []
        for block in blocks:
            contained = False

            for other in blocks:
                if (block is other):
                    continue

                if (block.file != other.file):
                    continue

                if ((other.start_line <= block.start_line)and(other.end_line >= block.end_line)
                and(other.start_line < block.start_line or other.end_line > block.end_line)):
                    contained = True
                    break

            if (not contained):
                result.append(block)

        result.sort(
            key=lambda block: (
                -block.score,
                block.file,
                block.start_line,
            )
        )

        return result
        '''
        # 高優先度から処理
        blocks = sorted(
            blocks,
            key=lambda block: (
                -block.score,
                block.file,
                block.start_line,
                block.end_line
            )
        )

        for block in blocks:
            contained = False

            for existing in result:
                if (block.file != existing.file):
                    continue

                # 既に採用した範囲に完全包含されている
                if ((existing.start_line <= block.start_line)and(existing.end_line >= block.end_line)):
                    contained = True
                    break

            if contained:
                continue

            result.append(block)

        return result
        '''