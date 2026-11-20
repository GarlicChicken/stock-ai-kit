"""예시 3: 이동평균 추세

20일 이동평균이 60일 이동평균보다 위에 있는(상승 추세) 종목 가운데
최근 20일 평균 거래대금이 큰 10종목을 담습니다. 그런 종목이 없으면 현금으로 둡니다.
"""

from kit.helpers import equal_weight, sma, top

NAME = "이동평균 추세"
DESCRIPTION = "20일선이 60일선 위에 있는 종목 중 거래대금이 큰 10종목을 담고 매주 다시 고릅니다."
REBALANCE = "weekly"

SHORT, LONG = 20, 60
TOP_N = 10


def decide(market):
    ma_short = sma(market.close, SHORT)
    ma_long = sma(market.close, LONG)
    if ma_long.empty:
        return {}
    rising = ma_long.index[ma_short.reindex(ma_long.index) > ma_long]
    value = market.amount.iloc[-SHORT:].mean()  # 최근 20일 평균 거래대금
    candidates = value[value.index.isin(rising) & value.index.isin(market.tradable())]
    return equal_weight(top(candidates, TOP_N))
