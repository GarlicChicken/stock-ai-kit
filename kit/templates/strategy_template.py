"""
내 전략 파일

- decide(market)는 리밸런싱하는 날 장이 끝난 뒤 불립니다.
  돌려준 {종목코드: 비중}대로 다음 거래일 시가에 사고팝니다.
- market에는 오늘까지의 데이터만 들어 있습니다. 미래 데이터는 볼 수 없습니다.
- 비중 합이 1보다 작으면 나머지는 현금으로 둡니다. 빈 사전 {}을 돌려주면 전부 현금입니다.
- 자세한 설명: docs/strategy-guide.md
"""

from kit.helpers import equal_weight, returns, top

NAME = "내 전략"
DESCRIPTION = "최근 20거래일 수익률이 높은 5종목을 같은 비중으로 담습니다."
REBALANCE = "weekly"  # daily(매일) · weekly(매주) · monthly(매달)


def decide(market):
    ret20 = returns(market.close, 20)
    if ret20.empty:
        return {}
    ret20 = ret20[ret20.index.isin(market.tradable())]
    return equal_weight(top(ret20, 5))
