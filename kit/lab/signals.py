"""기본 신호 모음. 모두 '그날 종가까지 알 수 있는 값'만으로 계산한다 (날짜 × 종목코드 표).

연구 노트북 · research 스크립트에서 쓰고, 전략 파일에서는 같은 계산을 market 표로 직접 한다.
값이 클수록 '사고 싶은 쪽'이 되도록 부호를 맞췄다 (예: 되돌림은 많이 떨어진 종목이 큰 값).
"""

import numpy as np
import pandas as pd


def momentum(panel, days=60, skip=0):
    """최근 days거래일 수익률 (skip일 전까지). 오른 종목이 큰 값."""
    c = panel.close
    return c.shift(skip) / c.shift(skip + days) - 1


def reversal(panel, days=5):
    """최근 days거래일 하락 폭. 많이 떨어진 종목이 큰 값 (단기 되돌림)."""
    return -(panel.close / panel.close.shift(days) - 1)


def low_volatility(panel, days=60):
    """최근 days거래일 변동성의 음수. 덜 흔들린 종목이 큰 값."""
    r = panel.close.pct_change(fill_method=None)
    return -r.rolling(days, min_periods=int(days * 0.8)).std()


def volume_shock(panel, days=20):
    """오늘 거래대금 ÷ 직전 days거래일 평균. 거래가 갑자기 늘어난 종목이 큰 값."""
    a = panel.amount.where(panel.amount > 0)
    return a / a.shift(1).rolling(days, min_periods=int(days * 0.8)).mean()


def gap(panel):
    """오늘 시가 ÷ 어제 종가 - 1 (시가 갭)."""
    return panel.open / panel.close.shift(1) - 1


def near_high(panel, days=250):
    """종가 ÷ 최근 days거래일 최고가. 신고가에 가까울수록 1에 가깝다."""
    c = panel.close
    return c / c.rolling(days, min_periods=int(days * 0.8)).max()


def size(panel):
    """시가총액(로그). 큰 회사가 큰 값."""
    m = panel.marcap.where(panel.marcap > 0)
    return np.log(m)


def small_size(panel):
    """시가총액(로그)의 음수. 작은 회사가 큰 값."""
    return -size(panel)


def turnover(panel, days=20):
    """최근 days거래일 평균 거래대금 ÷ 시가총액 (회전율)."""
    a = panel.amount.where(panel.amount > 0).rolling(days, min_periods=int(days * 0.8)).mean()
    return a / panel.marcap.where(panel.marcap > 0)


# 이름: (함수, 설명)
SIGNALS = {
    "momentum_20": (lambda p: momentum(p, 20), "최근 20거래일 수익률"),
    "momentum_60": (lambda p: momentum(p, 60), "최근 60거래일 수익률"),
    "momentum_12_1": (lambda p: momentum(p, 231, skip=21), "12개월 수익률 (최근 1개월 제외)"),
    "reversal_5": (lambda p: reversal(p, 5), "최근 5거래일 하락 폭 (단기 되돌림)"),
    "reversal_1": (lambda p: reversal(p, 1), "어제 하락 폭 (하루 되돌림)"),
    "low_vol_60": (lambda p: low_volatility(p, 60), "최근 60거래일 변동성이 낮을수록"),
    "volume_shock_20": (lambda p: volume_shock(p, 20), "거래대금이 평소보다 늘어난 정도"),
    "gap": (gap, "시가 갭 (시가 ÷ 전일 종가 - 1)"),
    "near_high_250": (lambda p: near_high(p, 250), "52주 최고가에 가까운 정도"),
    "size": (size, "시가총액이 클수록"),
    "small_size": (small_size, "시가총액이 작을수록"),
    "turnover_20": (lambda p: turnover(p, 20), "회전율 (거래대금 ÷ 시가총액)"),
}


def compute(panel, name):
    if name not in SIGNALS:
        raise KeyError(f"없는 신호입니다: {name}. 있는 신호: {', '.join(SIGNALS)}")
    return SIGNALS[name][0](panel)
