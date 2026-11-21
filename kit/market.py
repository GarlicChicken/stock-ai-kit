"""전략이 보는 시장 정보."""

import numpy as np
import pandas as pd


class Market:
    """decide(market)에 넘어가는 값. 오늘(today)까지의 데이터만 들어 있다.

    market.today         오늘 날짜
    market.dates         오늘까지의 거래일 목록
    market.open / high / low / close / volume
                         날짜 × 종목코드 표 (수정주가 · 수정 거래량). 마지막 줄이 오늘.
    market.amount        거래대금 (원)
    market.marcap        시가총액 (원)
    market.codes         데이터에 있는 모든 종목코드 (지금은 투자 대상이 아닌 종목도 포함)
    market.universe()    오늘의 투자 대상 (지난달 말 시가총액 상위 N종목)
    market.tradable()    투자 대상 중 오늘 정상 거래된 종목
    market.price()       오늘 실제 종가 (수정 전, 원)
    market.holdings      지금 들고 있는 종목과 비중 {종목코드: 비중}
    market.name(code) · market.market(code)  종목 이름(그날 기준) · 시장
    market.sector(code)  업종 (섹터분산용. 키트 업종표 기준, 없으면 '미분류')
    market.sectors(codes) 여러 종목의 업종 (Series)
    """

    def __init__(self, panel, i, holdings=None):
        self._panel = panel
        self._i = i
        self.today = panel.dates[i]
        self.dates = panel.dates[: i + 1]
        self.codes = list(panel.codes)
        self.holdings = dict(holdings or {})

    def _view(self, field):
        return getattr(self._panel, field).iloc[: self._i + 1]

    open = property(lambda self: self._view("open"))
    high = property(lambda self: self._view("high"))
    low = property(lambda self: self._view("low"))
    close = property(lambda self: self._view("close"))
    volume = property(lambda self: self._view("volume"))
    amount = property(lambda self: self._view("amount"))
    marcap = property(lambda self: self._view("marcap"))

    def universe(self):
        row = self._panel.member.iloc[self._i].to_numpy()
        return [c for c, m in zip(self.codes, row) if m]

    def tradable(self):
        member = self._panel.member.iloc[self._i].to_numpy()
        close = self._panel.close.iloc[self._i].to_numpy()
        volume = self._panel.volume.iloc[self._i].to_numpy()
        ok = member & np.isfinite(close) & (close > 0) & np.isfinite(volume) & (volume > 0)
        return [c for c, m in zip(self.codes, ok) if m]

    def price(self):
        return pd.Series(self._panel.price.iloc[self._i].to_numpy(), index=self.codes)

    def name(self, code):
        return self._panel.name_on(code, self.today)

    def market(self, code):
        return self._panel.market_on(code, self.today)

    def sector(self, code):
        return self._panel._s.get("sectors", {}).get(str(code), "미분류")

    def sectors(self, codes=None):
        codes = self.codes if codes is None else list(codes)
        table = self._panel._s.get("sectors", {})
        return pd.Series([table.get(str(c), "미분류") for c in codes], index=codes, dtype="object")

    def __repr__(self):
        return f"Market(today={self.today.date()}, days={len(self.dates)}, universe={len(self.universe())})"
