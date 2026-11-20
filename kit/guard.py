"""제출 전 전략 파일 점검.

다른 사람의 PC(진행자)에서 실행되므로, 파일·인터넷에 손대는 코드가 없는지 미리 본다.
완벽한 보안 장치는 아니고, 실수를 막는 점검이다.
"""

import ast
from pathlib import Path

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
    return sorted(set(problems))
