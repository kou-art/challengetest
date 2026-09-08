# Tree-sitter C variable analyzer

マイコンCをTree-sitter-cで構文解析し、対象変数をLLMへ説明させるためのコードだけを抽出する版です。

## インストール

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 実行

```powershell
python main.py
```

入力:

```text
Cプロジェクトのルートフォルダ: C:\path\to\project
調べたい変数名: g_temperature
```

出力:

```text
<project_root>\llm_context.txt
```

## 現在の抽出ルール

1. 対象変数の定義と宣言を取得する。
2. 対象変数の代入・参照・条件・引数・return・更新など全使用箇所を記録する。
3. 対象変数の使用箇所を含む関数は関数定義全体を取得する。関数宣言だけのものは出力しない。
4. 3の関数内で参照されるグローバル変数と呼び出し関数を取得する。関数は定義全体だけを出力する。
5. 対象変数の使用箇所に直接使われる定数は定義だけ取得する。
6. 対象変数の使用箇所に直接使われる関数は関数定義全体を取得する。
7. 次の変数を追跡対象にする。
   - 対象変数の使用箇所に直接使われる変数・field
   - 対象変数を使う関数内で参照されるグローバル変数
8. 7の変数について全使用箇所を記録し、その変数へ代入される値の定義を取得する。
   - 定数なら定義だけ
   - 関数なら関数定義全体
   - 変数ならその変数の定義
9. 7で見つけた変数から別の変数を無制限に再帰追跡しない。
10. Tree-sitterでシンボル解決が曖昧な場合、同名候補の先頭を勝手に採用しない。一意に特定できる場合はその1件を使い、特定できない場合は同名候補をすべて関連候補として残す。

## 出力

`llm_context.txt` は以下の3部構成です。

- `TARGET VARIABLE USAGES`: 対象変数の全使用箇所
- `RELATED VARIABLES`: 選択された関連変数の全使用箇所
- `RELATED SOURCE CODE`: 上記ルールで選択された定義・関数本体・定数

## 方針

Python側では意味を推測しません。Tree-sitterで構造的に確認できる関係だけを使って候補を抽出し、最終的な意味判断はLLMに任せます。
