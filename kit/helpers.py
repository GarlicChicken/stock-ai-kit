"""전략 파일에서 자주 쓰는 도구. `from kit.helpers import top, equal_weight` 처럼 불러 쓴다."""

import pandas as pd


class _Keep:
    """decide()가 KEEP을 돌려주면 이번에는 사고팔지 않고 들고 있는 그대로 둔다."""

    def __repr__(self):
        return "KEEP"


KEEP = _Keep()


def top(values, n):
    """값이 큰 순서로 n개 종목코드 목록. values: 종목코드가 index인 Series."""
    s = pd.Series(values).dropna()
    return s.sort_values(ascending=False, kind="mergesort").head(int(n)).index.tolist()


def bottom(values, n):
    """값이 작은 순서로 n개 종목코드 목록."""
    s = pd.Series(values).dropna()
    return s.sort_values(ascending=True, kind="mergesort").head(int(n)).index.tolist()


def equal_weight(codes):
    """종목들을 같은 비중으로 나눈 {종목코드: 비중}. 비어 있으면 {} (전부 현금)."""
    codes = list(codes)
    if not codes:
        return {}
    w = 1.0 / len(codes)
    return {c: w for c in codes}


def returns(close, days):
    """종목별 최근 days거래일 수익률 (Series). 데이터가 모자라면 빈 Series."""
    if len(close) <= days:
        return pd.Series(dtype="float64")
    return close.iloc[-1] / close.iloc[-1 - days] - 1


def sma(close, days):
    """종목별 최근 days거래일 단순 이동평균 (Series). 기간 안에 값이 빠진 종목은 제외."""
    window = close.iloc[-days:]
    if len(window) < days:
        return pd.Series(dtype="float64")
    full = window.notna().all()
    return window.mean()[full]


def only(values, codes):
    """values(Series)에서 codes에 든 종목만 남긴다."""
    s = pd.Series(values)
    return s[s.index.isin(list(codes))]


def limit_per_sector(codes, market, n):
    """codes를 앞에서부터 보며 업종마다 n종목까지만 남긴다 (섹터분산). 순서는 그대로."""
    out, count = [], {}
    for c in codes:
        sec = market.sector(c)
        if count.get(sec, 0) < int(n):
            out.append(c)
            count[sec] = count.get(sec, 0) + 1
    return out


def scale(weights, ratio):
    """비중을 ratio배로 줄인다. 예: scale(equal_weight(codes), 0.5) → 절반만 투자하고 나머지는 현금."""
    ratio = max(0.0, min(1.0, float(ratio)))
    return {c: w * ratio for c, w in dict(weights).items()}
