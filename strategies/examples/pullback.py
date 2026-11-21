"""예시 5: 눌림목

오르는 흐름(주가가 120일 평균 위) 속에서 최근 5거래일 동안 5% 넘게 내린 종목을 삽니다.
잠깐 쉬었다가 다시 오르는 자리를 노립니다. 매주 다시 골라, 조건에서 벗어난 종목은 팝니다.
고를 종목이 없으면 현금으로 기다립니다.
"""

from kit.helpers import bottom, equal_weight, only, returns, sma

NAME = "눌림목 8"
DESCRIPTION = "120일 평균 위 + 최근 5일 -5% 이하로 내린 종목 중 많이 내린 8종목, 매주 교체"
REBALANCE = "weekly"

TOP_N = 8
DIP = -0.05  # 최근 5일 수익률이 이보다 낮으면 '눌림'


def decide(market):
    close = market.close
    ma120 = sma(close, 120)
    if ma120.empty:
        return {}
    last = close.iloc[-1]
    trend = [c for c in market.tradable() if c in ma120.index and last[c] > ma120[c]]
    r5 = only(returns(close, 5), trend)
    dips = r5[r5 <= DIP]
    return equal_weight(bottom(dips, TOP_N))
