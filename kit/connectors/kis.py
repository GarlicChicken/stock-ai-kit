"""한국투자증권 Open API (조회 전용): 현재가 · 일봉 · 분봉 · 투자자별 매매동향.

키: KIS_APP_KEY · KIS_APP_SECRET (https://apiportal.koreainvestment.com, 계좌 개설 뒤 API 신청)
서버: KIS_ENV = mock(모의투자, 기본) · real(실전). 모의와 실전은 앱키가 따로다.
이 키트에는 주문 기능이 없고 만들지 않는다.

쓸 때 알아 둘 것
- 접근 토큰은 앱키당 1분에 1번만 발급된다(EGW00133). 받은 토큰은 .cache에 저장해 만료(약 24시간) 60초 전까지 다시 쓴다.
  같은 앱키를 쓰는 다른 프로그램이 있으면 토큰이 서로 겹칠 수 있다.
- 실전은 초당 약 20건 제한(EGW00201). 호출 사이를 띄운다. 모의 서버는 느리고(응답 30초 이상) 더 엄격하다.
- 응답 값은 모두 문자열이다. 단위가 API마다 다르다: 일봉 거래대금은 원, 투자자 순매수 대금은 백만원.
  이 모듈은 금액을 모두 '원'으로 바꿔 돌려준다.
- 당일 투자자 매매동향은 장 마감 전에는 비어 있다. 수급은 장 마감 뒤 공표되므로 다음 날 결정에만 쓴다.
- 과거 날짜를 요청하면 다른 날짜 행이 섞여 올 수 있어 날짜로 다시 거른다. 상장 전 날짜는 0으로 채워 와서 지운다.
- 분봉 시각은 '봉이 시작한 시각'이다. 실제로 쓸 수 있는 건 그 봉이 끝난 뒤다.
"""

import hashlib
import time

import pandas as pd

from ..console import KitError
from .base import cache_dir, get_key, read_json_cache, request, write_json_cache

HOSTS = {"real": "https://openapi.koreainvestment.com:9443", "mock": "https://openapivts.koreainvestment.com:29443"}
QUOTE = "/uapi/domestic-stock/v1/quotations"


def _env():
    env = (get_key("KIS_ENV", required=False) or "mock").lower()
    if env not in HOSTS:
        raise KitError("KIS_ENV는 mock 또는 real이어야 합니다.")
    return env


def _token():
    env = _env()
    app_key, app_secret = get_key("KIS_APP_KEY"), get_key("KIS_APP_SECRET")
    finger = hashlib.sha256(f"{env}:{app_key}".encode()).hexdigest()[:12]
    path = cache_dir("kis") / f"token_{finger}.json"
    cached = read_json_cache(path, max_age_sec=24 * 3600)
    if cached and cached.get("expires_at", 0) - 60 > time.time():
        return cached["access_token"]
    for attempt in range(2):
        r = request("POST", HOSTS[env] + "/oauth2/tokenP", host_key="kis-token", timeout=60, ok_status=(200, 403),
                    json={"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret})
        j = r.json()
        if j.get("access_token"):
            write_json_cache(path, {"access_token": j["access_token"],
                                    "expires_at": time.time() + int(j.get("expires_in", 86400))})
            return j["access_token"]
        if j.get("error_code") == "EGW00133" and attempt == 0:  # 1분에 1번 제한
            time.sleep(61)
            continue
        raise KitError(f"한국투자증권 토큰 발급 실패: {j.get('error_code', '')} {j.get('error_description', '')}")


def _get(path, tr_id, params):
    env = _env()
    headers = {
        "authorization": f"Bearer {_token()}",
        "appkey": get_key("KIS_APP_KEY"), "appsecret": get_key("KIS_APP_SECRET"),
        "tr_id": tr_id, "custtype": "P", "content-type": "application/json; charset=utf-8",
    }
    r = request("GET", HOSTS[env] + QUOTE + path, headers=headers, params=params, host_key=f"kis-{env}",
                min_interval=0.07 if env == "real" else 0.5, timeout=60)
    try:
        j = r.json()
    except ValueError:
        j = {"rt_cd": "?", "msg1": r.content.decode("cp949", errors="replace")[:200]}
    if j.get("rt_cd") != "0":
        raise KitError(f"한국투자증권 오류 {j.get('msg_cd', '')}: {j.get('msg1', '')}")
    return j


def _num(s, mult=1):
    s = str(s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s) * mult
    except ValueError:
        return None


def price(code):
    """현재가 등 (stck_prpr 현재가, hts_frgn_ehrt 외국인 소진율, lstn_stcn 상장주식수 등)."""
    j = _get("/inquire-price", "FHKST01010100", {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(code).zfill(6)})
    o = j.get("output", {})
    return {"code": str(code).zfill(6), "price": _num(o.get("stck_prpr")), "change_rate": _num(o.get("prdy_ctrt")),
            "volume": _num(o.get("acml_vol")), "amount": _num(o.get("acml_tr_pbmn")),
            "foreign_ratio": _num(o.get("hts_frgn_ehrt")), "shares": _num(o.get("lstn_stcn")), "raw": o}


def daily(code, start, end=None, adjusted=True):
    """일봉 (수정주가 기본). 한 번에 100행씩 뒤로 넘기며 받는다. 열: date, open, high, low, close, volume, amount(원)"""
    code = str(code).zfill(6)
    start = pd.Timestamp(start)
    cur = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
    rows = []
    while cur >= start:
        j = _get("/inquire-daily-itemchartprice", "FHKST03010100", {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": start.strftime("%Y%m%d"), "FID_INPUT_DATE_2": cur.strftime("%Y%m%d"),
            "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0" if adjusted else "1"})
        got = [r for r in j.get("output2", []) if r.get("stck_bsop_date")]
        if not got:
            break
        rows.extend(got)
        earliest = pd.Timestamp(min(r["stck_bsop_date"] for r in got))
        if len(got) < 90 or earliest <= start:
            break
        cur = earliest - pd.Timedelta(days=1)
    if not rows:
        return pd.DataFrame(columns=["date", "code", "open", "high", "low", "close", "volume", "amount"])
    df = pd.DataFrame({
        "date": pd.to_datetime([r["stck_bsop_date"] for r in rows], format="%Y%m%d"),
        "code": code,
        "open": [_num(r.get("stck_oprc")) for r in rows], "high": [_num(r.get("stck_hgpr")) for r in rows],
        "low": [_num(r.get("stck_lwpr")) for r in rows], "close": [_num(r.get("stck_clpr")) for r in rows],
        "volume": [_num(r.get("acml_vol")) for r in rows], "amount": [_num(r.get("acml_tr_pbmn")) for r in rows],
    })
    df = df[(df["date"] >= start) & (df["close"].fillna(0) > 0)]
    return df.drop_duplicates("date").sort_values("date").reset_index(drop=True)


def minutes_today(code, until="153000"):
    """오늘 1분봉 (until 시각부터 09:00까지 30개씩 거꾸로). 열: datetime(봉 시작 시각), close, volume"""
    code = str(code).zfill(6)
    hour, rows, seen = until, [], set()
    for _ in range(20):
        j = _get("/inquire-time-itemchartprice", "FHKST03010200", {
            "FID_ETC_CLS_CODE": "", "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
            "FID_INPUT_HOUR_1": hour, "FID_PW_DATA_INCU_YN": "Y"})
        got = [r for r in j.get("output2", []) if r.get("stck_cntg_hour") and r["stck_cntg_hour"] not in seen]
        if not got:
            break
        for r in got:
            seen.add(r["stck_cntg_hour"])
        rows.extend(got)
        earliest = min(r["stck_cntg_hour"] for r in got)
        if earliest <= "090000":
            break
        t = pd.Timestamp(f"2000-01-01 {earliest[:2]}:{earliest[2:4]}:{earliest[4:]}") - pd.Timedelta(minutes=1)
        hour = t.strftime("%H%M%S")
    if not rows:
        return pd.DataFrame(columns=["datetime", "code", "close", "volume"])
    day = rows[0].get("stck_bsop_date") or pd.Timestamp.today().strftime("%Y%m%d")
    df = pd.DataFrame({
        "datetime": pd.to_datetime([f"{r.get('stck_bsop_date', day)}{r['stck_cntg_hour']}" for r in rows], format="%Y%m%d%H%M%S"),
        "code": code, "close": [_num(r.get("stck_prpr")) for r in rows], "volume": [_num(r.get("cntg_vol")) for r in rows],
    })
    return df.sort_values("datetime").reset_index(drop=True)


def investor_flows(code):
    """최근 약 30거래일 투자자별 순매수 (개인 · 외국인 · 기관). 금액은 원. 오늘 행은 장 마감 뒤에만 채워진다."""
    j = _get("/inquire-investor", "FHKST01010900", {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": str(code).zfill(6)})
    rows = [r for r in j.get("output", []) if r.get("stck_bsop_date")]
    df = pd.DataFrame({
        "date": pd.to_datetime([r["stck_bsop_date"] for r in rows], format="%Y%m%d"),
        "code": str(code).zfill(6),
        "close": [_num(r.get("stck_clpr")) for r in rows],
        "individual_qty": [_num(r.get("prsn_ntby_qty")) for r in rows],
        "foreign_qty": [_num(r.get("frgn_ntby_qty")) for r in rows],
        "institution_qty": [_num(r.get("orgn_ntby_qty")) for r in rows],
        "individual_amount": [_num(r.get("prsn_ntby_tr_pbmn"), 1_000_000) for r in rows],
        "foreign_amount": [_num(r.get("frgn_ntby_tr_pbmn"), 1_000_000) for r in rows],
        "institution_amount": [_num(r.get("orgn_ntby_tr_pbmn"), 1_000_000) for r in rows],
    })
    return df.dropna(subset=["foreign_qty"], how="all").sort_values("date").reset_index(drop=True)


def ping():
    p = price("005930")
    return f"삼성전자 현재가 {p['price']:,.0f}원 ({_env()} 서버)"
