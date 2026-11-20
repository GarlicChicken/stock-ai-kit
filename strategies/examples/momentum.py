"""예시 2: 모멘텀

최근 60거래일 동안 많이 오른 10종목을 같은 비중으로 담고, 매주 다시 고릅니다.
"오른 종목이 조금 더 오른다"는 가정을 시험합니다.
"""

from kit.helpers import equal_weight, returns, top

NAME = "모멘텀 상위 10"
DESCRIPTION = "최근 60거래일 수익률이 높은 10종목을 같은 비중으로 담고 매주 다시 고릅니다."
REBALANCE = "weekly"

LOOKBACK = 60  # 수익률을 재는 기간 (거래일)
TOP_N = 10     # 담을 종목 수


def decide(market):
    ret = returns(market.close, LOOKBACK)
    if ret.empty:
        return {}
    ret = ret[ret.index.isin(market.tradable())]
    return equal_weight(top(ret, TOP_N))
