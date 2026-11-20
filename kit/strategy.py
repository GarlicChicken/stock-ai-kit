"""전략 파일 불러오기."""

import importlib.util
import itertools
from dataclasses import dataclass
from pathlib import Path

from .console import KitError

REBALANCE = {"daily": "매일", "weekly": "매주", "monthly": "매달"}
_counter = itertools.count()


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
    rebalance = str(getattr(module, "REBALANCE", "weekly")).lower()
    if rebalance not in REBALANCE:
        raise KitError(f"REBALANCE는 daily · weekly · monthly 중 하나여야 합니다 (지금: {rebalance})")
    return Strategy(
        path=path,
        name=str(getattr(module, "NAME", path.stem)),
        description=str(getattr(module, "DESCRIPTION", "")),
        rebalance=rebalance,
        decide=decide,
    )
