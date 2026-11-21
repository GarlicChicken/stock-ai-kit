"""전략 파일 점검 (backtest · submit 전에 자동으로 한다).

1. 다른 사람의 PC(진행자)에서도 실행되므로, 파일 · 인터넷에 손대는 코드가 없는지 본다.
2. 이미 아는 결과로 고르지 않도록, 종목코드 · 종목 이름 · 업종 이름 · 날짜 · 연도를 코드에 직접 적었는지 본다.
   (업종은 market.sector()로 분산에만 쓴다. 특정 업종을 골라 사는 규칙은 안 된다.)
완벽한 보안 장치는 아니고, 실수를 막는 점검이다.
"""

import ast
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .paths import REFERENCE

CODE_RE = re.compile(r"^(\d{6}|\d{4}[A-Z]\d)$")
DATE_RE = re.compile(r"^(19|20)\d\d[-./]?(0[1-9]|1[0-2])([-./]?\d\d)?$")

ALLOWED_IMPORTS = {
    "pandas", "numpy", "math", "statistics", "datetime", "functools", "itertools",
    "collections", "typing", "dataclasses", "kit.helpers",
}
BANNED_CALLS = {
    "open", "exec", "eval", "compile", "__import__", "input", "breakpoint",
    "globals", "locals", "vars", "getattr", "setattr", "delattr",
}
BANNED_ATTRS = {
    "to_csv", "to_excel", "to_parquet", "to_pickle", "to_json", "to_sql", "to_hdf",
    "to_feather", "to_html", "to_clipboard", "to_stata", "to_latex", "to_markdown", "to_xml",
    # numpy 파일 읽기 · 쓰기
    "load", "loadtxt", "genfromtxt", "fromfile", "memmap", "save", "savetxt", "savez",
    "savez_compressed", "tofile", "DataSource",
    # pandas 파일 도구
    "HDFStore", "ExcelFile", "ExcelWriter",
}


@lru_cache(maxsize=1)
def _reference_words():
    """업종표에 있는 종목 이름 · 업종 이름."""
    path = REFERENCE / "sectors.csv"
    if not path.exists():
        return frozenset(), frozenset()
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    names = frozenset(n.strip() for n in df["name"].dropna() if len(n.strip()) >= 2)
    sectors = frozenset(x.strip() for x in df["sector"].dropna() if x.strip() and x.strip() != "미분류")
    return names, sectors


def _literal_problems(tree):
    names, sectors = _reference_words()
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.strip()
            if CODE_RE.match(v):
                problems.append((node.lineno, f"종목코드를 직접 적을 수 없습니다: '{v}' (모든 종목에 같은 조건으로 골라 주세요)"))
            elif v in names:
                problems.append((node.lineno, f"종목 이름을 직접 적을 수 없습니다: '{v}'"))
            elif v in sectors:
                problems.append((node.lineno, f"업종 이름을 직접 적을 수 없습니다: '{v}' (업종은 분산에만 씁니다)"))
            elif DATE_RE.match(v):
                problems.append((node.lineno, f"날짜를 직접 적을 수 없습니다: '{v}' (규칙은 날짜와 상관없이 같아야 합니다)"))
        elif isinstance(node, ast.Compare):
            parts = [node.left, *node.comparators]
            uses_year = any(isinstance(x, ast.Attribute) and x.attr == "year" for x in parts)
            years = [x.value for x in parts if isinstance(x, ast.Constant) and isinstance(x.value, int)
                     and not isinstance(x.value, bool) and 1990 <= x.value <= 2100]
            if uses_year and years:
                problems.append((node.lineno, f"특정 연도를 조건으로 쓸 수 없습니다: {years[0]}"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "name":
            problems.append((node.lineno, "종목 이름으로 고를 수 없습니다: .name() 은 전략에서 쓰지 않습니다"))
    return problems


def _import_ok(name):
    return name in ALLOWED_IMPORTS or name.split(".")[0] in {"pandas", "numpy"}


def check_file(path):
    """문제 목록 [(줄, 설명)]을 돌려준다. 비어 있으면 통과."""
    path = Path(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as e:
        return [(e.lineno or 0, f"문법 오류: {e.msg}")]
    problems = []
    has_decide = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if not _import_ok(a.name):
                    problems.append((node.lineno, f"허용되지 않은 import: {a.name}"))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level or not (_import_ok(mod) or (mod == "kit" and all(a.name == "helpers" for a in node.names))):
                problems.append((node.lineno, f"허용되지 않은 import: from {'.' * node.level}{mod}"))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in BANNED_CALLS:
            problems.append((node.lineno, f"쓸 수 없는 함수: {node.func.id}()"))
        elif isinstance(node, ast.Name) and node.id.startswith("__") and node.id.endswith("__") and node.id != "__name__":
            problems.append((node.lineno, f"쓸 수 없는 이름: {node.id}"))
        elif isinstance(node, ast.Attribute):
            if node.attr in BANNED_ATTRS or node.attr.startswith("read_"):
                problems.append((node.lineno, f"파일·시스템에 접근하는 기능은 쓸 수 없습니다: .{node.attr}"))
            elif node.attr.startswith("_"):
                problems.append((node.lineno, f"밑줄(_)로 시작하는 내부 속성은 쓸 수 없습니다: .{node.attr}"))
        elif isinstance(node, ast.FunctionDef) and node.name == "decide" and node in tree.body:
            has_decide = len(node.args.args) >= 1
    if not has_decide:
        problems.append((0, "파일 맨 바깥에 decide(market) 함수가 있어야 합니다."))
    problems += _literal_problems(tree)
    return sorted(set(problems))
