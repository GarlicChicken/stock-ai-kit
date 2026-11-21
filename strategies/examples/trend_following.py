"""예시 4: 추세추종 (2주마다 리밸런싱)

오르는 흐름에 올라탑니다. 주가가 60일 · 120일 평균보다 모두 위에 있는(상승 추세) 종목 가운데
최근 120거래일 수익률이 높은 10종목을 같은 비중으로 담고, 2주마다 다시 고릅니다.
추세가 꺾여 평균 아래로 내려온 종목은 다음 리밸런싱 때 빠집니다.
"""

from kit.helpers import equal_weight, only, returns, sma, top

NAME = "추세추종 10"
DESCRIPTION = "60 · 120일 평균 위에 있는 종목 중 120일 수익률 상위 10종목, 2주마다 교체"
REBALANCE = "2weeks"  # 3weeks로 바꾸면 3주마다

TOP_N = 10


def decide(market):
    close = market.close
    ma60, ma120 = sma(close, 60), sma(close, 120)
    if ma120.empty:
        return {}
    last = close.iloc[-1]
    up = [c for c in market.tradable() if c in ma120.index and last[c] > ma60[c] and last[c] > ma120[c]]
    ret = only(returns(close, 120), up)
    return equal_weight(top(ret, TOP_N))
