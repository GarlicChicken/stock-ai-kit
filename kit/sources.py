"""데이터 출처 공통 함수.

출처(FinanceDataReader · yfinance · pykrx)가 달라도 같은 모양으로 돌려준다.
- 일봉: date, code, open, high, low, close, volume
- 분봉: datetime, code, open, high, low, close, volume
출처별 특징과 한계는 docs/data-sources.md 에 정리돼 있다.
"""

import contextlib
import io

import pandas as pd

from .console import KitError
from .paths import CACHE

DAILY_COLUMNS = ["date", "code", "open", "high", "low", "close", "volume"]
MINUTE_COLUMNS = ["datetime", "code", "open", "high", "low", "close", "volume"]
INDEXES = {"KOSPI": "KS11", "KOSDAQ": "KQ11"}

# yfinance 분봉 한 번에 받을 수 있는 최대 일수 (2026-11 확인)
MINUTE_LIMIT_DAYS = {"1m": 8, "2m": 60, "5m": 60, "15m": 60, "30m": 60, "60m": 730, "1h": 730}

_yf_ready = False


def _naive(index):
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_convert("Asia/Seoul").tz_localize(None)
    return idx


def _frame(index, code, src, names, time_col="date"):
    if src is None or len(src) == 0:
        return pd.DataFrame(columns=MINUTE_COLUMNS if time_col == "datetime" else DAILY_COLUMNS)
    o, h, l, c, v = names
    out = pd.DataFrame({
        time_col: _naive(index),
        "code": code,
        "open": src[o].to_numpy(),
        "high": src[h].to_numpy(),
        "low": src[l].to_numpy(),
        "close": src[c].to_numpy(),
        "volume": src[v].to_numpy(),
    })
    return out.dropna(subset=["close"]).reset_index(drop=True)


def _ts(value):
    return pd.Timestamp(value) if value is not None else None


# ---------------------------------------------------------------- FinanceDataReader

def _fdr():
    import FinanceDataReader as fdr
    return fdr


def _fdr_daily(code, start, end):
    df = _fdr().DataReader(code, start, end)
    return _frame(df.index if df is not None else [], code, df, ("Open", "High", "Low", "Close", "Volume"))


# ---------------------------------------------------------------- yfinance

def _yf():
    global _yf_ready
    import yfinance as yf
    if not _yf_ready:
        (CACHE / "yfinance").mkdir(parents=True, exist_ok=True)
        try:
            yf.set_tz_cache_location(str(CACHE / "yfinance"))
        except Exception:
            pass
        _yf_ready = True
    return yf


def _yahoo_symbols(code, market):
    if market == "KOSPI":
        return [f"{code}.KS"]
    if market == "KOSDAQ":
        return [f"{code}.KQ"]
    return [f"{code}.KS", f"{code}.KQ"]


def _yahoo_daily(code, start, end, market):
    yf = _yf()
    end_excl = (end + pd.Timedelta(days=1)) if end is not None else None
    for symbol in _yahoo_symbols(code, market):
        df = yf.Ticker(symbol).history(start=start, end=end_excl, interval="1d", auto_adjust=False)
        if df is not None and len(df):
            return _frame(df.index, code, df, ("Open", "High", "Low", "Close", "Volume"))
    return _frame([], code, None, None)


# ---------------------------------------------------------------- pykrx

def _pykrx_stock():
    # pykrx는 불러올 때 KRX 로그인 안내 문구를 출력한다. 일봉은 로그인 없이 되므로 숨긴다.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        from pykrx import stock
    return stock


def _pykrx_daily(code, start, end):
    stock = _pykrx_stock()
    end = end or pd.Timestamp.today()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        df = stock.get_market_ohlcv(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), code)
    return _frame(df.index if df is not None else [], code, df, ("시가", "고가", "저가", "종가", "거래량"))


# ---------------------------------------------------------------- 공개 함수

def get_daily(code, start="2020-01-01", end=None, source="fdr", market=None):
    """한 종목의 일봉을 받는다.

    code: 종목코드 6자리 (예: "005930")
    source: "fdr"(FinanceDataReader, 기본) · "yahoo"(yfinance) · "pykrx"
    market: "KOSPI" 또는 "KOSDAQ" (yahoo에서 접미사 .KS/.KQ를 고를 때 씀)
    """
    code = str(code).zfill(6)
    start, end = _ts(start), _ts(end)
    if source == "fdr":
        return _fdr_daily(code, start, end)
    if source == "yahoo":
        return _yahoo_daily(code, start, end, market)
    if source == "pykrx":
        return _pykrx_daily(code, start, end)
    raise KitError(f"알 수 없는 출처입니다: {source} (fdr · yahoo · pykrx 중 선택)")


def get_minute(code, interval="1m", days=5, market=None):
    """한 종목의 분봉을 받는다 (yfinance).

    interval: "1m" · "2m" · "5m" · "15m" · "30m" · "60m"
    days: 최근 며칠. 1분봉은 한 번에 최대 8일, 5분봉 등은 60일, 60분봉은 730일까지.
    """
    code = str(code).zfill(6)
    limit = MINUTE_LIMIT_DAYS.get(interval)
    if limit is None:
        raise KitError(f"지원하지 않는 간격입니다: {interval}")
    days = max(1, min(int(days), limit))
    yf = _yf()
    for symbol in _yahoo_symbols(code, market):
        df = yf.Ticker(symbol).history(period=f"{days}d", interval=interval, auto_adjust=False)
        if df is not None and len(df):
            return _frame(df.index, code, df, ("Open", "High", "Low", "Close", "Volume"), time_col="datetime")
    return _frame([], code, None, None, time_col="datetime")


def get_listing(market="KRX"):
    """지금 상장된 종목 목록 (FinanceDataReader). 장중에는 시가총액이 비어 올 때가 있다."""
    df = _fdr().StockListing(market)
    cols = {"Code": "code", "Name": "name", "Market": "market", "Marcap": "marcap"}
    df = df.rename(columns=cols)
    keep = [c for c in cols.values() if c in df.columns]
    return df[keep].reset_index(drop=True)


def marcap_available(year):
    """marcap 원천 파일(그해)이 열리는지 확인한다 (내려받지 않고 주소만 확인)."""
    import requests

    url = f"https://github.com/FinanceData/marcap/raw/master/data/marcap-{int(year)}.parquet"
    r = requests.head(url, allow_redirects=True, timeout=20)
    return r.status_code == 200


def get_marcap(year):
    """한 해의 거래소 전 종목 일별 데이터 (상장폐지 종목 포함). .cache/marcap/에 받아 두고 읽는다.

    열: Code, Name, Market, Date, Open, High, Low, Close, Changes, Volume, Amount, Marcap
    가격은 그날 실제 가격(수정 전)이다.
    """
    from .data import fetch_marcap, read_marcap

    fetch_marcap(int(year))
    return read_marcap(int(year))


def get_index(name="KOSPI", start="2000-01-01", end=None):
    """지수 일봉 종가 (FinanceDataReader). name: "KOSPI" · "KOSDAQ" 또는 기호(KS11 등)."""
    symbol = INDEXES.get(name, name)
    df = _fdr().DataReader(symbol, _ts(start), _ts(end))
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date", "name", "close"])
    return pd.DataFrame({"date": _naive(df.index), "name": name, "close": df["Close"].to_numpy()}).dropna()
