"""한국거래소(KRX) Open API: 하루치 전 종목 시세 (거래소 공식 값).

키: KRX_AUTH_KEY (https://openapi.krx.co.kr 회원가입 > 인증키 신청 > 쓸 API마다 '이용 신청' 후 승인)
한도: 키당 하루 1만 건. 약관상 받은 데이터를 다른 사람에게 다시 나눠 주면 안 된다.

- daily(date, market): 그날 코스피 · 코스닥 전 종목의 시가 · 고가 · 저가 · 종가 · 거래량 · 거래대금 · 시가총액
- 값이 수정주가인지는 공식 문서로 확인하지 못했다 (그날 실제 가격으로 보인다).
- 응답 값의 '-'는 값 없음.
"""

import pandas as pd

from ..console import KitError
from .base import get_key, request

BASE = "https://data-dbg.krx.co.kr/svc/apis/sto"
SERVICES = {"KOSPI": "stk_bydd_trd", "KOSDAQ": "ksq_bydd_trd"}


def _num(s):
    s = str(s or "").replace(",", "").strip()
    return None if s in ("", "-") else float(s)


def daily(date, market="KOSPI"):
    if market not in SERVICES:
        raise KitError("market은 KOSPI 또는 KOSDAQ입니다.")
    key = get_key("KRX_AUTH_KEY")
    d = pd.Timestamp(date).strftime("%Y%m%d")
    r = request("GET", f"{BASE}/{SERVICES[market]}", params={"basDd": d, "AUTH_KEY": key},
                host_key="krx", min_interval=0.2)
    j = r.json()
    rows = j.get("OutBlock_1", [])
    if not rows and j.get("respMsg"):
        raise KitError(f"KRX 오류: {j.get('respMsg')}")
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "code", "name", "open", "high", "low", "close", "volume", "amount", "marcap"])
    return pd.DataFrame({
        "date": pd.to_datetime(df["BAS_DD"], format="%Y%m%d"),
        "code": df["ISU_CD"], "name": df["ISU_NM"], "market": market,
        "open": df["TDD_OPNPRC"].map(_num), "high": df["TDD_HGPRC"].map(_num), "low": df["TDD_LWPRC"].map(_num),
        "close": df["TDD_CLSPRC"].map(_num), "volume": df["ACC_TRDVOL"].map(_num), "amount": df["ACC_TRDVAL"].map(_num),
        "marcap": df["MKTCAP"].map(_num),
    })


def ping():
    for back in range(1, 8):
        d = pd.Timestamp.today().normalize() - pd.Timedelta(days=back)
        df = daily(d, "KOSPI")
        if len(df):
            return f"{d.date()} 코스피 {len(df)}종목"
    return "최근 일주일 데이터 없음"
