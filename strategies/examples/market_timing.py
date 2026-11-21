"""예시 7: 현금 비중 조절

시가총액 상위 20종목을 같은 비중으로 담되, 시장 분위기에 따라 투자 비중을 바꿉니다.
시장 분위기 = 투자 대상 가운데 주가가 200일 평균보다 위에 있는 종목의 비율.
  50% 이상이면 전부 투자, 30~50%면 절반만 투자, 30% 아래면 전부 현금.
"""

from kit.helpers import equal_weight, scale, sma, top

NAME = "현금 비중 조절 20"
DESCRIPTION = "시총 상위 20 동일 비중, 200일 평균 위 종목 비율로 투자 비중 100 · 50 · 0%"
REBALANCE = "weekly"


def decide(market):
    close = market.close
    ma200 = sma(close, 200)
    codes = [c for c in market.tradable() if c in ma200.index]
    if not codes:
        return {}
    last = close.iloc[-1]
    breadth = sum(last[c] > ma200[c] for c in codes) / len(codes)
    ratio = 1.0 if breadth >= 0.5 else 0.5 if breadth >= 0.3 else 0.0
    caps = market.marcap.iloc[-1]
    picks = top(caps[caps.index.isin(codes)], 20)
    return scale(equal_weight(picks), ratio)
