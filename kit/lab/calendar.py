"""거래일 · 시점 처리.

- 거래일은 데이터에 실제로 있는 날짜로 정한다 (공휴일 목록을 손으로 적지 않는다).
- 장이 끝난 뒤(15:30 이후)나 휴장일에 나온 정보(공시 · 뉴스)는 다음 거래일에 쓸 수 있는 정보로 본다.
- 시각은 한국 시각(KST) 기준으로 다룬다.
"""

import pandas as pd

MARKET_CLOSE = pd.Timedelta(hours=15, minutes=30)


def trading_days(panel):
    """데이터에 있는 거래일 목록 (DatetimeIndex)."""
    return pd.DatetimeIndex(panel.dates)


def shift_trading_day(days, date, n=1):
    """date 기준 n거래일 뒤(음수면 앞) 거래일. date가 휴장일이면 다음 거래일을 1거래일 뒤로 센다."""
    days = pd.DatetimeIndex(days)
    d = pd.Timestamp(date).normalize()
    i = int(days.searchsorted(d))
    if i < len(days) and days[i] == d:
        j = i + n
    else:
        j = i + n - 1 if n > 0 else i + n
    return days[j] if 0 <= j < len(days) else pd.NaT


def effective_day(days, when):
    """정보가 나온 시각(when)을, 그 정보로 처음 결정할 수 있는 거래일로 바꾼다.

    결정은 그 거래일 장 마감 뒤에 하고, 체결은 다음 거래일 시가로 한다고 본다.
    - 시각이 있으면: 거래일 15:30 전 -> 그날 / 15:30 이후 -> 다음 거래일
    - 날짜만 있으면: 그날 장 마감까지 알았다고 보고 그날
    - 휴장일이면: 다음 거래일
    """
    days = pd.DatetimeIndex(days)
    ts = pd.Timestamp(when)
    day = ts.normalize()
    i = int(days.searchsorted(day))
    if i >= len(days):
        return pd.NaT
    if days[i] != day:
        return days[i]
    if ts != day and (ts - day) >= MARKET_CLOSE:
        return days[i + 1] if i + 1 < len(days) else pd.NaT
    return day
