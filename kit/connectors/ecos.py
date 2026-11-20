"""한국은행 ECOS (경제통계시스템): 금리 · 환율 · 물가 · 통화량 · 경기 지표.

키: ECOS_API_KEY (https://ecos.bok.or.kr/api > 인증키 신청, 무료)
키가 없으면 시험용 키("sample")로 한 번에 10건까지만 받아진다.

주소 형식: https://ecos.bok.or.kr/api/{서비스}/{키}/json/kr/{시작 번호}/{끝 번호}/{통계표 코드}/{주기}/{시작}/{끝}/{항목 코드...}
- 주기: D(일) · M(월) · Q(분기) · A(연). 날짜 형식: D=YYYYMMDD, M=YYYYMM, Q=YYYYQn, A=YYYY
- 통계표 · 항목 코드는 search_tables() · items()로 찾는다. 자주 쓰는 것은 POPULAR에 모아 두었다.

쓸 때 알아 둘 것
- 발표일과 기준일이 다르다 (예: 월간 물가는 다음 달 초에 발표). 날짜(기준일)를 그대로 주가와 붙이면
  미래 데이터를 쓰는 셈이 된다. 월간 지표는 최소 한 달 늦춰(shift) 붙인다.
"""

import pandas as pd

from ..console import KitError
from .base import get_key, request

BASE = "https://ecos.bok.or.kr/api"

# 이름: (통계표 코드, 주기, 항목 코드1, 설명)  ※ kit keys test로 확인한 코드
POPULAR = {
    "기준금리": ("722Y001", "D", "0101000", "한국은행 기준금리 (%)"),
    "국고채3년": ("817Y002", "D", "010200000", "국고채 3년 금리 (%)"),
    "국고채10년": ("817Y002", "D", "010210000", "국고채 10년 금리 (%)"),
    "원달러환율": ("731Y001", "D", "0000001", "원/달러 환율 (매매기준율, 원)"),
    "소비자물가": ("901Y009", "M", "0", "소비자물가지수 총지수 (2020=100)"),
    "M2": ("161Y005", "M", "BBHS00", "M2 광의통화 평잔 (계절조정, 십억원)"),
}


def _key():
    return get_key("ECOS_API_KEY", required=False) or "sample"


def _fetch(service, *path, start=1, end=1000):
    key = _key()
    if key == "sample":
        end = min(end, 10)
    url = "/".join([BASE, service, key, "json", "kr", str(start), str(end), *[str(p) for p in path]])
    j = request("GET", url, host_key="ecos", min_interval=0.2).json()
    if "RESULT" in j:
        code, msg = j["RESULT"].get("CODE", ""), j["RESULT"].get("MESSAGE", "")
        if code == "INFO-200":  # 데이터 없음
            return []
        raise KitError(f"ECOS 오류 {code}: {msg}")
    body = j.get(service, {})
    return body.get("row", [])


def series(stat_code, freq, start, end, *item_codes):
    """통계 값. 예: series("722Y001", "D", "20240101", "20241231", "0101000")
    돌려주는 열: date, value, unit, stat_name, item_name
    """
    items = list(item_codes) or ["?"]
    rows = _fetch("StatisticSearch", stat_code, freq, start, end, *items, start=1, end=100000)
    if not rows:
        return pd.DataFrame(columns=["date", "value", "unit", "stat_name", "item_name"])
    df = pd.DataFrame(rows)
    fmt = {"D": "%Y%m%d", "M": "%Y%m", "A": "%Y"}.get(freq)
    dates = pd.PeriodIndex(df["TIME"].str.replace("Q", "-Q"), freq="Q").to_timestamp() if freq == "Q" \
        else pd.to_datetime(df["TIME"], format=fmt)
    return pd.DataFrame({
        "date": dates,
        "value": pd.to_numeric(df["DATA_VALUE"], errors="coerce"),
        "unit": df.get("UNIT_NAME", ""),
        "stat_name": df.get("STAT_NAME", ""),
        "item_name": df.get("ITEM_NAME1", ""),
    }).sort_values("date").reset_index(drop=True)


def get(name, start, end):
    """자주 쓰는 지표를 이름으로. 예: get("기준금리", "20200101", "20241231")
    날짜 형식은 그 지표의 주기에 맞춘다 (일: YYYYMMDD, 월: YYYYMM)."""
    if name not in POPULAR:
        raise KitError(f"없는 이름입니다: {name}. 있는 이름: {', '.join(POPULAR)}")
    code, freq, item, _ = POPULAR[name]
    return series(code, freq, start, end, item)


def search_tables(keyword):
    """통계표 목록에서 이름에 keyword가 들어간 것."""
    rows = _fetch("StatisticTableList", start=1, end=10000)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    hit = df[df["STAT_NAME"].str.contains(keyword, na=False)]
    return hit[[c for c in ("STAT_CODE", "STAT_NAME", "CYCLE", "SRCH_YN") if c in hit]].reset_index(drop=True)


def items(stat_code):
    """통계표의 항목 코드 목록."""
    df = pd.DataFrame(_fetch("StatisticItemList", stat_code, start=1, end=10000))
    cols = [c for c in ("ITEM_CODE", "ITEM_NAME", "CYCLE", "START_TIME", "END_TIME", "UNIT_NAME") if c in df]
    return df[cols] if len(df) else df


def key_stats():
    """한국은행이 고른 100대 통계지표의 최근 값."""
    df = pd.DataFrame(_fetch("KeyStatisticList", start=1, end=100))
    cols = [c for c in ("CLASS_NAME", "KEYSTAT_NAME", "DATA_VALUE", "CYCLE", "UNIT_NAME") if c in df]
    return df[cols] if len(df) else df


def ping():
    df = key_stats()
    return f"100대 지표 {len(df)}건 ({'시험용 키' if _key() == 'sample' else '내 키'})"
