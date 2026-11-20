"""예시 1: 동일 비중

거래되는 모든 종목을 같은 비중으로 담고, 매달 비중을 다시 맞춥니다.
다른 전략과 비교하는 기준선으로 쓰기 좋습니다.
"""

from kit.helpers import equal_weight

NAME = "동일 비중"
DESCRIPTION = "거래되는 모든 종목을 같은 비중으로 담고 매달 비중을 다시 맞춥니다."
REBALANCE = "monthly"


def decide(market):
    return equal_weight(market.tradable())
