"""해외 시세 · 지표 (키 필요 없음): 미국 지수 · 환율 · 원자재 · 미국 금리 등.

- prices(symbol): yfinance 일봉 종가. 예: ^GSPC(S&P500) · ^IXIC(나스닥) · ^SOX(반도체) · ^VIX · KRW=X(원/달러)
  · CL=F(원유) · GC=F(금) · ^N225(닛케이) · 000001.SS(상하이)
- fred(series_id): 미국 연준 FRED 경제지표. 예: DGS10(미국 10년 금리) · DEXKOUS(원/달러) · FEDFUNDS(기준금리) · CPIAUCSL(물가)
  FRED 값은 '지금 기준 최신값'이라, 나중에 고쳐진 숫자가 섞여 있다 (발표 당시 값이 아님).

시점 주의 (한국 장과 붙일 때)
- 미국 · 유럽 시장은 한국 장이 끝난 뒤 열린다. 미국 날짜 t의 종가는 한국 t+1 장 전에 알 수 있다.
  한국 t일 장 마감 뒤 결정에 쓸 수 있는 미국 값은 t-1일 종가까지로 보는 것이 안전하다.
- 환율 · 원자재 · 암호화폐 일봉은 날짜 경계가 한국 개장 무렵이라, 한국 t일 결정에는 t-2일 값까지만 쓰는 편이 안전하다.
"""

import io

import pandas as pd

from .base import request


def prices(symbol, start="2015-01-01", end=None):
    """yfinance 일봉 종가 (분할 · 배당 반영). 열: date, symbol, close"""
    from ..sources import _yf

    yf = _yf()
    e = (pd.Timestamp(end) + pd.Timedelta(days=1)) if end else None  # end는 그날을 빼고 받으므로 하루 더한다
    df = yf.Ticker(symbol).history(start=start, end=e, interval="1d", auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "symbol", "close"])
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return pd.DataFrame({"date": idx.normalize(), "symbol": symbol, "close": df["Close"].to_numpy()}).reset_index(drop=True)


def fred(series_id, start=None):
    """FRED 경제지표 (키 없이 CSV로). 열: date, series, value ('.'은 값 없음)"""
    r = request("GET", "https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series_id},
                host_key="fred", min_interval=0.5, timeout=60)
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df.insert(1, "series", series_id)
    if start:
        df = df[df["date"] >= pd.Timestamp(start)]
    return df.reset_index(drop=True)


def ping():
    df = fred("DGS10", start=pd.Timestamp.today() - pd.Timedelta(days=30))
    return f"FRED 미국 10년 금리 {len(df)}일"
