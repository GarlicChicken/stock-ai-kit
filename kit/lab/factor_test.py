"""신호(팩터) 검증: 신호가 앞으로의 수익률을 얼마나 맞히는지 본다.

- 진입: 신호를 계산한 날(t) 장 마감 뒤 결정 -> 다음 거래일(t+1) 시가에 산다고 본다.
- 앞으로의 수익률: t+1 시가 -> t+horizon 종가.
- 비교 대상: 그날의 투자 대상(시가총액 상위 N) 중 값이 있는 종목.
- IC: 날짜마다 신호 순위와 앞으로 수익률 순위의 상관 (스피어만). 0.02~0.05만 꾸준해도 쓸모가 있다고 본다.
- 5분위: 신호 순으로 5묶음을 나눠 묶음별 평균 수익률. 맨 위 - 맨 아래가 '롱숏 차이'.
비용은 빼지 않은 값이다. 실제로 쓸 수 있는지는 백테스트(비용 포함)로 다시 확인한다.
"""

import math

import numpy as np
import pandas as pd


def forward_returns(panel, horizon=5):
    """날짜 t 행에: t+1 시가 -> t+horizon 종가 수익률."""
    entry = panel.open.shift(-1)
    exit_ = panel.close.shift(-horizon)
    return exit_ / entry - 1


def _aligned(sig, fwd, member):
    s = sig.where(member & sig.notna() & fwd.notna())
    return s, fwd.where(s.notna())


def _rank_ic(sig, fwd, member, min_names):
    """날짜마다 신호 순위와 수익률 순위의 상관 (표 전체를 한 번에 계산)."""
    s, f = _aligned(sig, fwd, member)
    n = s.notna().sum(axis=1)
    rs, rf = s.rank(axis=1), f.rank(axis=1)
    rs = rs.sub(rs.mean(axis=1), axis=0)
    rf = rf.sub(rf.mean(axis=1), axis=0)
    ic = (rs * rf).sum(axis=1) / np.sqrt((rs ** 2).sum(axis=1) * (rf ** 2).sum(axis=1))
    return ic[n >= min_names].dropna()


def _quantiles(sig, fwd, member, q, min_names):
    """날짜마다 신호 순으로 q묶음을 나눈 묶음별 평균 수익률."""
    s, f = _aligned(sig, fwd, member)
    n = s.notna().sum(axis=1)
    bins = np.ceil(s.rank(axis=1, method="first", pct=True) * q).clip(1, q)
    out = pd.DataFrame({k: f.where(bins == k).mean(axis=1) for k in range(1, q + 1)})
    return out[n >= min_names].dropna(how="all").sort_index()


def t_stat(series, lag=0):
    """평균의 t값. lag>0이면 겹치는 기간 때문에 생기는 자기상관을 줄여 계산(Newey-West)."""
    x = pd.Series(series).dropna().to_numpy()
    n = len(x)
    if n < 3:
        return float("nan")
    e = x - x.mean()
    var = (e @ e) / n
    for k in range(1, lag + 1):
        w = 1 - k / (lag + 1)
        var += 2 * w * (e[k:] @ e[:-k]) / n
    se = math.sqrt(max(var, 1e-18) / n)
    return float(x.mean() / se)


def test(signal, panel, horizon=5, quantiles=5, start=None, end=None, min_names=20):
    """신호를 검증해 요약 · 표를 돌려준다.

    signal: 날짜 × 종목코드 표 (kit.lab.signals의 결과 또는 직접 만든 표)
    """
    sig = signal.reindex(index=panel.close.index, columns=panel.close.columns)
    fwd = forward_returns(panel, horizon)
    member = panel.member
    days = sig.index
    keep = np.ones(len(days), dtype=bool)
    if start is not None:
        keep &= days >= pd.Timestamp(start)
    if end is not None:
        keep &= days <= pd.Timestamp(end)
    keep[-(horizon + 1):] = False  # 앞으로 수익률이 아직 없는 마지막 날들
    sig, fwd, member = sig[keep], fwd[keep], member[keep]

    ic = _rank_ic(sig, fwd, member, min_names)
    qret = _quantiles(sig, fwd, member, quantiles, min_names)
    if ic.empty or qret.empty:
        raise ValueError("검증할 날짜가 없습니다 (기간 · 신호 값을 확인해 주세요).")
    spread = qret[quantiles] - qret[1]
    yearly = pd.DataFrame({
        "ic": ic.groupby(ic.index.year).mean(),
        "spread": spread.groupby(spread.index.year).mean(),
        "days": ic.groupby(ic.index.year).size(),
    })
    summary = {
        "start": str(ic.index[0].date()),
        "end": str(ic.index[-1].date()),
        "days": int(len(ic)),
        "horizon": int(horizon),
        "ic_mean": round(float(ic.mean()), 4),
        "ic_t": round(t_stat(ic, lag=horizon), 2),
        "ic_positive_share": round(float((ic > 0).mean()), 3),
        "spread_mean": round(float(spread.mean()), 5),
        "spread_t": round(t_stat(spread, lag=horizon), 2),
        "years_same_sign": int((np.sign(yearly["ic"]) == np.sign(ic.mean())).sum()),
        "years": int(len(yearly)),
        "quantile_mean": {int(k): round(float(v), 5) for k, v in qret.mean().items()},
    }
    return {"summary": summary, "ic": ic, "quantiles": qret, "spread": spread, "yearly": yearly}
