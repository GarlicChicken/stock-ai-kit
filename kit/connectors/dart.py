"""OpenDART (금융감독원 전자공시): 공시 목록 · 기업 개황 · 재무제표.

키: DART_API_KEY (https://opendart.fss.or.kr 회원가입 > 인증키 신청, 무료)
한도: 키당 하루 약 2만 건(공식 안내 확인). 넘으면 상태 코드 020.

쓸 때 알아 둘 것
- 공시 목록의 rcept_dt는 '접수 날짜'만 있고 시각이 없다. 장 마감 뒤 접수도 많으므로(약 4건 중 1건),
  보수적으로 '접수일 장 마감 뒤에 알았다'고 보고 다음 거래일 시가에 반응한다고 가정한다 (kit.lab.calendar).
- 재무제표 숫자는 사업연도가 끝난 날이 아니라 '공시된 날'부터 쓸 수 있다. 결과의 available_date(접수일)를 쓴다.
- 공시일은 권리락일 · 효력 발생일이 아니다.
- 보고서 이름의 가운뎃점이 'ㆍ' · '·' 두 가지로 섞여 와서 '·'로 맞춘다.
"""

import io
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from ..console import KitError
from .base import cache_dir, get_key, request

BASE = "https://opendart.fss.or.kr/api"
STATUS = {
    "000": "정상", "010": "등록되지 않은 키", "011": "사용할 수 없는 키", "012": "접근할 수 없는 IP",
    "013": "조회된 데이터 없음", "014": "파일이 없음", "020": "하루 사용 한도 초과", "021": "조회 가능한 회사 개수 초과",
    "100": "필드 값 오류", "101": "부적절한 접근", "800": "시스템 점검 중", "900": "정의되지 않은 오류",
}
KINDS = {  # 공시 유형 (pblntf_ty)
    "A": "정기공시", "B": "주요사항보고", "C": "발행공시", "D": "지분공시", "E": "기타공시",
    "F": "외부감사관련", "G": "펀드공시", "H": "자산유동화", "I": "거래소공시", "J": "공정위공시",
}
REPORTS = {"annual": "11011", "half": "11012", "q1": "11013", "q3": "11014"}  # 사업 · 반기 · 1분기 · 3분기 보고서


def _get(path, **params):
    key = get_key("DART_API_KEY")
    r = request("GET", f"{BASE}/{path}", params={"crtfc_key": key, **params}, host_key="dart", min_interval=0.3)
    j = r.json()
    status = str(j.get("status", ""))
    if status == "013":
        return None
    if status != "000":
        raise KitError(f"DART 오류 {status} ({STATUS.get(status, '')}): {j.get('message', '')}")
    return j


# ---------------------------------------------------------------- 고유번호

def corp_codes(refresh=False):
    """전체 회사 고유번호 표 (corp_code, corp_name, stock_code). 상장사만 stock_code가 있다. 7일간 캐시."""
    import time

    path = cache_dir("dart") / "corpCode.zip"
    if refresh or not path.exists() or time.time() - path.stat().st_mtime > 7 * 86400:
        key = get_key("DART_API_KEY")
        r = request("GET", f"{BASE}/corpCode.xml", params={"crtfc_key": key}, host_key="dart", min_interval=0.3, timeout=60)
        if not r.content.startswith(b"PK"):
            raise KitError(f"DART 고유번호 파일을 받지 못했습니다: {r.text[:200]}")
        path.write_bytes(r.content)
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    rows = [{k: (item.findtext(k) or "").strip() for k in ("corp_code", "corp_name", "stock_code", "modify_date")}
            for item in root.iter("list")]
    return pd.DataFrame(rows)


def corp_code(stock_code):
    """종목코드(6자리) -> DART 고유번호(8자리)."""
    df = corp_codes()
    hit = df[df["stock_code"] == str(stock_code).zfill(6)]
    if hit.empty:
        raise KitError(f"{stock_code}에 해당하는 DART 고유번호가 없습니다.")
    return hit["corp_code"].iloc[0]


# ---------------------------------------------------------------- 공시 목록

def _norm_title(s):
    return str(s or "").replace("ㆍ", "·").strip()


def filings(stock_code=None, start=None, end=None, kind=None, final_only=True, max_pages=100):
    """공시 목록. stock_code를 주면 그 회사만, 안 주면 전체(90일 단위로 나눠 조회).

    kind: 공시 유형 한 글자 (KINDS 참고, 예: "B" 주요사항보고). 기간 기본값: 최근 30일.
    돌려주는 열: date(접수일), corp_name, stock_code, report(보고서명), rcept_no, filer, remark, kind, url
    """
    end = pd.Timestamp(end) if end else pd.Timestamp.today().normalize()
    start = pd.Timestamp(start) if start else end - pd.Timedelta(days=30)
    base = {"last_reprt_at": "Y" if final_only else "N", "page_count": 100}
    if stock_code:
        base["corp_code"] = corp_code(stock_code)
    if kind:
        base["pblntf_ty"] = kind
    windows = []
    step = pd.Timedelta(days=89 if not stock_code else 3 * 365)
    s = start
    while s <= end:
        e = min(s + step, end)
        windows.append((s, e))
        s = e + pd.Timedelta(days=1)
    rows = []
    for s, e in windows:
        page = 1
        while page <= max_pages:
            j = _get("list.json", bgn_de=s.strftime("%Y%m%d"), end_de=e.strftime("%Y%m%d"), page_no=page, **base)
            if not j:
                break
            rows.extend(j.get("list", []))
            if page >= int(j.get("total_page", 1)):
                break
            page += 1
    if not rows:
        return pd.DataFrame(columns=["date", "corp_name", "stock_code", "report", "rcept_no", "filer", "remark", "kind", "url"])
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "date": pd.to_datetime(df["rcept_dt"], format="%Y%m%d"),
        "corp_name": df["corp_name"],
        "stock_code": df.get("stock_code", "").fillna(""),
        "report": df["report_nm"].map(_norm_title),
        "rcept_no": df["rcept_no"],
        "filer": df.get("flr_nm", ""),
        "remark": df.get("rm", ""),
        "kind": kind or "",
        "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + df["rcept_no"],
    })
    return out.drop_duplicates("rcept_no").sort_values(["date", "rcept_no"]).reset_index(drop=True)


# ---------------------------------------------------------------- 기업 개황 · 재무제표

def company(stock_code):
    """기업 개황 (회사명 · 대표자 · 업종코드 · 결산월 · 설립일 등)."""
    j = _get("company.json", corp_code=corp_code(stock_code))
    return {k: v for k, v in (j or {}).items() if k not in ("status", "message")}


def _amount(s):
    s = str(s or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def financials(stock_code, year, report="annual", consolidated=True, full=False):
    """재무제표 한 기간.

    - full=False: 주요 계정 (매출액 · 영업이익 · 당기순이익 · 자산 · 부채 · 자본 등, fnlttSinglAcnt)
    - full=True : 전체 계정 (fnlttSinglAcntAll)
    report: annual(사업보고서) · half(반기) · q1 · q3. 금액 단위: 원.
    돌려주는 열: year, report, statement, account, this_term, prev_term, prev2_term, fs, available_date, rcept_no
    """
    params = {"corp_code": corp_code(stock_code), "bsns_year": str(year), "reprt_code": REPORTS[report]}
    if full:
        params["fs_div"] = "CFS" if consolidated else "OFS"
        j = _get("fnlttSinglAcntAll.json", **params)
    else:
        j = _get("fnlttSinglAcnt.json", **params)
    rows = (j or {}).get("list", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if not full and "fs_div" in df:
        df = df[df["fs_div"] == ("CFS" if consolidated else "OFS")]
        if df.empty:  # 연결재무제표가 없는 회사
            df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "year": int(year), "report": report,
        "statement": df.get("sj_nm", df.get("sj_div", "")),
        "account": df["account_nm"].str.strip(),
        "this_term": df["thstrm_amount"].map(_amount),
        "prev_term": df.get("frmtrm_amount", pd.Series([None] * len(df), index=df.index)).map(_amount),
        "prev2_term": df.get("bfefrmtrm_amount", pd.Series([None] * len(df), index=df.index)).map(_amount),
        "fs": df.get("fs_nm", df.get("fs_div", "")),
        "rcept_no": df["rcept_no"],
    })
    out["available_date"] = pd.to_datetime(out["rcept_no"].str[:8], format="%Y%m%d")
    return out.reset_index(drop=True)


def key_accounts(stock_code, years, report="annual", accounts=("매출액", "영업이익", "당기순이익")):
    """여러 해의 주요 계정을 표로 (행: 연도, 열: 계정). available_date도 함께."""
    rows = []
    for y in years:
        df = financials(stock_code, y, report=report)
        if df.empty:
            continue
        row = {"year": int(y), "available_date": df["available_date"].iloc[0]}
        names = df["account"].str.replace(r"\s|\(.*?\)", "", regex=True)  # '당기순이익(손실)' -> '당기순이익'
        for a in accounts:
            hit = df[names == a]
            if hit.empty:
                hit = df[names.str.contains(a, regex=False)]
            row[a] = hit["this_term"].iloc[0] if len(hit) else None
        rows.append(row)
    return pd.DataFrame(rows)


def key_accounts_many(stock_codes, year, report="annual", consolidated=True,
                      accounts=("매출액", "영업이익", "당기순이익")):
    """여러 회사의 한 해 주요 계정을 한 번에 (다중회사 주요계정 API, 100개씩 묶어 호출).

    돌려주는 열: code, year, available_date, 매출액, 영업이익, 당기순이익 (단위: 원)
    """
    table = corp_codes().set_index("stock_code")["corp_code"]
    codes = [str(c).zfill(6) for c in stock_codes]
    pairs = [(c, table.get(c)) for c in codes if table.get(c)]
    rows = []
    for k in range(0, len(pairs), 100):
        chunk = pairs[k:k + 100]
        j = _get("fnlttMultiAcnt.json", corp_code=",".join(p[1] for p in chunk), bsns_year=str(year),
                 reprt_code=REPORTS[report])
        rows.extend((j or {}).get("list", []))
    if not rows:
        return pd.DataFrame(columns=["code", "year", "available_date", *accounts])
    df = pd.DataFrame(rows)
    want = "CFS" if consolidated else "OFS"
    has_cfs = set(df.loc[df["fs_div"] == want, "stock_code"])
    df = df[(df["fs_div"] == want) | ~df["stock_code"].isin(has_cfs)]  # 연결이 없으면 별도
    df["name"] = df["account_nm"].str.replace(r"\s|\(.*?\)", "", regex=True)
    out = []
    for code, g in df.groupby("stock_code"):
        row = {"code": code, "year": int(year), "available_date": pd.to_datetime(g["rcept_no"].iloc[0][:8], format="%Y%m%d")}
        for a in accounts:
            hit = g[g["name"] == a]
            if hit.empty:
                hit = g[g["name"].str.contains(a, regex=False)]
            row[a] = _amount(hit["thstrm_amount"].iloc[0]) if len(hit) else None
        out.append(row)
    return pd.DataFrame(out)


def ping():
    df = filings(start=pd.Timestamp.today() - pd.Timedelta(days=3))
    return f"최근 3일 공시 {len(df)}건"
