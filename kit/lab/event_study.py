"""이벤트 스터디: 어떤 일(공시 · 뉴스 등)이 있은 뒤 주가가 평균적으로 어떻게 움직였는지 본다.

- 이벤트 표: date(또는 날짜+시각), code 열. 시각이 있으면 15:30 이후 · 휴장일 이벤트는 다음 거래일로 옮긴다.
- 진입: 이벤트를 안 거래일 장 마감 뒤 결정 -> 다음 거래일 시가.
- 초과수익: 같은 날 투자 대상 종목 평균(동일 비중)과의 차이.
- 결과: 1~horizon거래일 누적 초과수익(CAR) 평균 · t값 · 플러스 비율, 이벤트별 표.
비용은 빼지 않은 값이다.
"""

import numpy as np
import pandas as pd

from .calendar import effective_day
from .factor_test import t_stat


def run(events, panel, horizon=10):
    ev = events.copy()
    if "code" not in ev or "date" not in ev:
        raise ValueError("이벤트 표에는 date · code 열이 있어야 합니다.")
    ev["code"] = ev["code"].astype(str).str.zfill(6)
    days = panel.dates
    ev["decide"] = [effective_day(days, w) for w in ev["date"]]
    ev = ev.dropna(subset=["decide"])
    open_, close, member = panel.open, panel.close, panel.member
    bench_ret = close.where(member).pct_change(fill_method=None).mean(axis=1)  # 투자 대상 평균 하루 수익률
    index = {d: i for i, d in enumerate(days)}
    paths, rows = [], []
    for e in ev.itertuples(index=False):
        if e.code not in close.columns:
            continue
        i = index.get(pd.Timestamp(e.decide))
        if i is None or i + horizon >= len(days):
            continue
        entry = open_.iat[i + 1, close.columns.get_loc(e.code)]
        if not np.isfinite(entry) or entry <= 0:
            continue
        px = close.iloc[i + 1:i + 1 + horizon][e.code].to_numpy()
        stock = px / entry - 1
        # 첫날은 시가 -> 종가, 이후는 종가 -> 종가로 시장 평균을 이어 붙인다
        first_bench = (close.iloc[i + 1].where(member.iloc[i + 1]) / open_.iloc[i + 1].where(member.iloc[i + 1]) - 1).mean()
        bench = np.cumprod(np.r_[1 + first_bench, 1 + bench_ret.iloc[i + 2:i + 1 + horizon].to_numpy()]) - 1
        car = stock - bench
        paths.append(car)
        rows.append({"date": e.date, "code": e.code, "decide": pd.Timestamp(e.decide).date(),
                     "entry": round(float(entry), 2), f"car_{horizon}": round(float(car[-1]), 5)})
    if not paths:
        raise ValueError("계산할 수 있는 이벤트가 없습니다 (날짜 · 종목코드 · 데이터 기간을 확인해 주세요).")
    paths = pd.DataFrame(paths, columns=range(1, horizon + 1))
    curve = pd.DataFrame({
        "day": range(1, horizon + 1),
        "car_mean": paths.mean().round(5).to_numpy(),
        "t": [round(t_stat(paths[c]), 2) for c in paths.columns],
        "positive_share": (paths > 0).mean().round(3).to_numpy(),
    })
    summary = {"events": int(len(paths)), "horizon": horizon,
               "car_mean": round(float(paths[horizon].mean()), 5), "t": round(t_stat(paths[horizon]), 2),
               "positive_share": round(float((paths[horizon] > 0).mean()), 3)}
    return {"summary": summary, "curve": curve, "events": pd.DataFrame(rows)}
