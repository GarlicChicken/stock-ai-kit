"""전략 파일 불러오기."""

import importlib.util
import itertools
import re
from dataclasses import dataclass
from pathlib import Path

from .console import KitError

REBALANCE = {"daily": "매일", "weekly": "매주", "monthly": "매달"}
_UNITS = {"day": "거래일", "week": "주", "month": "달"}
_PATTERN = re.compile(r"^(\d+)\s*(day|days|week|weeks|month|months)$")
_counter = itertools.count()


def parse_rebalance(value):
    """REBALANCE 값을 (단위, 몇 번마다)로 바꾼다.

    "daily" · "weekly" · "monthly" 또는 "2weeks" · "3weeks" · "10days"(거래일) · "2months" 처럼 적는다.
    """
    text = str(value).strip().lower().replace("_", "").replace("-", "")
    simple = {"daily": ("day", 1), "weekly": ("week", 1), "monthly": ("month", 1),
              "biweekly": ("week", 2), "quarterly": ("month", 3)}
    if text in simple:
        return simple[text]
    m = _PATTERN.match(text)
    if m and int(m.group(1)) >= 1:
        unit = m.group(2).rstrip("s")
        return unit, int(m.group(1))
    raise KitError("REBALANCE는 daily · weekly · monthly 또는 2weeks · 3weeks · 10days · 2months 처럼 적어야 합니다 "
                   f"(지금: {value})")


def rebalance_label(value):
    """화면에 보일 말: 매일 · 매주 · 2주마다 · 10거래일마다 · 매달 · 2달마다."""
    unit, n = parse_rebalance(value)
    if n == 1:
        return {"day": "매일", "week": "매주", "month": "매달"}[unit]
    return f"{n}{_UNITS[unit]}마다"


@dataclass
class Strategy:
    path: Path
    name: str
    description: str
    rebalance: str
    decide: object


def load_strategy(path):
    """전략 파일을 새로 불러온다 (부를 때마다 새 모듈이라 이전 실행의 상태가 남지 않는다)."""
    path = Path(path).resolve()
    if not path.exists():
        raise KitError(f"전략 파일이 없습니다: {path}")
    spec = importlib.util.spec_from_file_location(f"kit_strategy_{next(_counter)}", path)
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        raise KitError(f"전략 파일을 불러오지 못했습니다: {type(e).__name__}: {e}") from e
    decide = getattr(module, "decide", None)
    if not callable(decide):
        raise KitError("전략 파일에 decide(market) 함수가 없습니다.")
    rebalance = str(getattr(module, "REBALANCE", "weekly")).strip().lower()
    parse_rebalance(rebalance)  # 잘못 적었으면 여기서 알려 준다
    return Strategy(
        path=path,
        name=str(getattr(module, "NAME", path.stem)),
        description=str(getattr(module, "DESCRIPTION", "")),
        rebalance=rebalance,
        decide=decide,
    )
