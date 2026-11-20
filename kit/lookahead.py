"""미래 데이터 · 무작위 결정 검사.

같은 전략을 '전체 기간'과 '중간에서 자른 기간'으로 돌려, 겹치는 날의 결정이 같은지 비교한다.
- 엔진은 오늘까지의 데이터만 넘기므로, 결정이 다르면 숨은 경로로 미래 데이터를 보거나
  실행할 때마다 결과가 달라지는(무작위) 코드가 있다는 뜻이다.
- 파일을 직접 읽는 우회는 이 검사로 잡히지 않는다. 그건 코드 점검(guard)이 막는다.
"""

import pandas as pd

from .engine import run_backtest
from .strategy import load_strategy


def _decisions(weights):
    out = {}
    for d, g in weights.groupby("date"):
        out[d] = {c: round(w, 6) for c, w in zip(g["code"], g["weight"]) if c}
    return out


def check(path, panel, cfg, start, end):
    """(통과 여부, 설명) 을 돌려준다."""
    dates = panel.dates
    s = int(dates.searchsorted(pd.Timestamp(start)))
    e = int(dates.searchsorted(pd.Timestamp(end), side="right")) - 1
    if e - s < 40:
        return True, "기간이 짧아 검사를 건너뜁니다."
    full = _decisions(run_backtest(load_strategy(path), panel, cfg, start, end).weights)
    for frac in (0.5, 0.75):
        cut = s + int((e - s) * frac)
        part = _decisions(run_backtest(load_strategy(path), panel.until(cut), cfg, start, dates[cut]).weights)
        for d in sorted(part):
            if d >= dates[cut]:
                continue
            if full.get(d, {}) != part[d]:
                return False, (f"{d.date()}의 결정이 데이터를 {dates[cut].date()}까지만 줬을 때와 다릅니다. "
                               "미래 데이터를 쓰거나, 실행할 때마다 결과가 달라지는(무작위) 코드가 있을 수 있습니다.")
    return True, "겹치는 날의 결정이 모두 같습니다."
