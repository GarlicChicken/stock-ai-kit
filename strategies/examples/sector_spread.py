"""예시 6: 섹터분산

모멘텀(최근 60거래일 수익률) 순위로 고르되, 한 업종에서는 최대 2종목만 담아
여러 업종에 나눠 투자합니다. 업종은 market.sector(code)로 봅니다 (특정 업종을 지정해 고르지는 않습니다).
"""

from kit.helpers import equal_weight, limit_per_sector, returns, top

NAME = "섹터분산 모멘텀 10"
DESCRIPTION = "60일 수익률 순위로 고르되 업종마다 최대 2종목, 10종목, 매달 교체"
REBALANCE = "monthly"

TOP_N = 10
PER_SECTOR = 2


def decide(market):
    ret = returns(market.close, 60)
    if ret.empty:
        return {}
    ret = ret[ret.index.isin(market.tradable())]
    ranked = top(ret, len(ret))
    return equal_weight(limit_per_sector(ranked, market, PER_SECTOR)[:TOP_N])
