"""데이터 만들기 · 묶기 · 풀기 · 확인 · 불러오기.

표준 데이터 (data/ 폴더, 다른 폴더에도 같은 모양으로 만들 수 있음)
- prices.parquet : 날짜 · 종목코드 · 이름 · 시장 · 시가 · 고가 · 저가 · 종가 · 전일 대비 · 거래량 · 거래대금 · 상장주식수
                   (모두 그날 거래소가 발표한 실제 값. 수정주가 · 시가총액은 불러올 때 계산)
- universe.csv   : 매달 마지막 거래일의 시가총액 상위 N종목 (그날부터 다음 달 말까지 투자 대상)
- stocks.csv     : 종목 이름 · 시장 · 첫 거래일 · 마지막 거래일 · 상장폐지 여부
- index.csv      : 코스피 · 코스닥 지수 종가
- manifest.json  : 만든 날 · 기간 · 데이터 지문

원천: FinanceData/marcap (한국거래소 전 종목 일별 데이터, 1995년~, 상장폐지 종목 포함)
"""

import hashlib
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import sources
from .console import KitError, warn
from .paths import CACHE, DATA, MINUTE, OUTPUTS

KST = timezone(timedelta(hours=9))
MARCAP_URL = "https://github.com/FinanceData/marcap/raw/master/data/marcap-{year}.parquet"
MARCAP_FIRST_YEAR = 1995
RAW_COLUMNS = ["Code", "Name", "Market", "Date", "Open", "High", "Low", "Close", "Changes",
               "Volume", "Amount", "Marcap", "Stocks"]
PRICE_COLUMNS = ["date", "code", "name", "market", "open", "high", "low", "close", "change", "volume", "amount", "shares"]
INT_COLUMNS = PRICE_COLUMNS[4:]
FILES = ("prices.parquet", "universe.csv", "stocks.csv", "index.csv", "manifest.json")


def now_kst():
    return datetime.now(KST)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def folder_of(folder=None):
    return Path(folder) if folder else DATA


# ---------------------------------------------------------------- 원천 데이터 (marcap)

def marcap_file(year):
    return CACHE / "marcap" / f"marcap-{year}.parquet"


def fetch_marcap(year, refresh=False, log=print):
    """연도별 원천 파일을 .cache/marcap/에 받아 둔다. 올해 파일은 6시간이 지나면 새로 받는다."""
    path = marcap_file(year)
    this_year = now_kst().year
    stale = path.exists() and year >= this_year and time.time() - path.stat().st_mtime > 6 * 3600
    if path.exists() and not refresh and not stale:
        return path
    import requests

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    last_error = None
    for attempt in range(3):
        try:
            with requests.get(MARCAP_URL.format(year=year), stream=True, timeout=60) as r:
                if r.status_code == 404:
                    return None
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            os.replace(tmp, path)
            log(f"  {year}년 원천 파일 받음 ({path.stat().st_size / 1e6:.0f}MB)")
            return path
        except Exception as e:  # 네트워크 오류는 두 번 더 시도
            last_error = e
            time.sleep(2 * (attempt + 1))
    if path.exists():
        warn(f"{year}년 파일을 새로 받지 못해 이전에 받은 파일을 씁니다 ({type(last_error).__name__})")
        return path
    raise KitError(f"{year}년 원천 데이터를 받지 못했습니다: {type(last_error).__name__}. 인터넷 연결을 확인해 주세요.")


def read_marcap(year):
    """한 해의 원천 데이터 (코스피 · 코스닥만)."""
    path = marcap_file(year)
    if not path.exists():
        return None
    d = pd.read_parquet(path, columns=RAW_COLUMNS)
    d = d[d["Market"].isin(["KOSPI", "KOSDAQ", "KOSDAQ GLOBAL"])].copy()
    d["Market"] = d["Market"].replace({"KOSDAQ GLOBAL": "KOSDAQ"})
    # 2000-05-26 이전 원천 기록은 종목코드 앞의 0이 빠져 있다 (5930 -> 005930)
    d["Code"] = d["Code"].astype(str).str.strip().str.zfill(6)
    d["Name"] = d["Name"].fillna("").astype(str)
    d["Date"] = pd.to_datetime(d["Date"])
    return d


# ---------------------------------------------------------------- 만들기

# 일반 회사가 아닌 투자 기구는 투자 대상에서 뺀다 (코스피200도 이런 종목은 뺀다).
# 원천 데이터에 종목 구분 칸이 없어 이름 규칙과 고정 목록을 같이 쓴다.
FUND_NAMES = {
    "맥쿼리인프라", "이리츠코크렙", "맵스리얼티1",  # 인프라펀드 · 리츠
    # 1999~2001년 상장 뮤추얼펀드 중 이름이 '호' · 'MF'로 끝나지 않는 것
    "SEI에셋", "드림", "트윈스비전일", "마이다스성일", "마이다스페셜", "사파이어전환", "옵티멈전환일",
    "박현주자산1", "박현주2성장", "박현주4성장",
}
# 같은 종목코드가 펀드 이름과 다른 이름을 함께 쓴 경우 (1995~2026 원천 데이터에서 찾음, 2026-11-18)
FUND_CODES = {
    "035030", "035930", "037500", "037510", "038280", "038370", "039370", "042950", "044740", "044890",
    "045070", "045280", "045550", "045790", "045800", "045860", "046520", "046820", "047890", "048660",
    "049990", "051070", "051990", "052520", "052530", "052540", "053530", "063680",  # 뮤추얼펀드 (나중에 MF가 붙음)
    "081930",  # 선박투자회사 (아시아8호 -> 아시아퍼시픽8)
    "121550",  # 리츠 (코크렙15호 -> 코크렙십오호)
}
NOT_FUND_NAMES = {"인터리츠"}  # 이름이 '리츠'로 끝나지만 일반 회사


def is_fund(name, code=None):
    """뮤추얼펀드 · 선박투자회사(이름이 '숫자+호' 또는 'MF'로 끝남), 리츠(이름이 '리츠'로 끝남), 인프라펀드."""
    name = str(name).strip()
    if code in FUND_CODES or name in FUND_NAMES or re.search(r"(\d+호|MF)$", name):
        return True
    return name.endswith("리츠") and name not in NOT_FUND_NAMES


def _eligible(d):
    """순위에 넣을 종목: 보통주(6자리 코드의 끝자리가 0. 2025년부터 쓰는 영문 섞인 코드 예: 0126Z0 포함),
    스팩 · 투자 기구(is_fund) 제외, 시가총액 있음. 우선주(끝자리 5 · 7 · 9 또는 영문, 예: 005935 · 00680K)는 빠진다."""
    e = d[d["Code"].str.fullmatch(r"[0-9A-Z]{5}0") & ~d["Name"].str.contains("스팩", regex=False) & (d["Marcap"] > 0)]
    pairs = e[["Code", "Name"]].drop_duplicates()
    funds = {(c, n) for c, n in pairs.itertuples(index=False) if is_fund(n, c)}
    if not funds:
        return e
    key = pd.MultiIndex.from_arrays([e["Code"], e["Name"]])
    return e[~key.isin(list(funds))]


def build_dataset(load, years, start, end, top_n):
    """원천 데이터로 표준 데이터를 만든다.

    load(year) -> 그해 원천 DataFrame (RAW_COLUMNS). years: 읽을 연도 목록 (start 전 해 포함).
    돌려주는 값: prices, universe, stocks (DataFrame)
    """
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    # 1) 매달 마지막 거래일의 시가총액 순위
    month_last = {}
    for y in years:
        d = load(y)
        if d is None or d.empty:
            continue
        d = d[d["Date"] <= end]
        if d.empty:
            continue
        e = _eligible(d)
        for period, day in e.groupby(e["Date"].dt.to_period("M"))["Date"].max().items():
            month_last[period] = (day, e[e["Date"] == day])
    all_months = sorted(month_last)
    ranks = []
    for i, period in enumerate(all_months):
        day, rows = month_last[period]
        complete = (i + 1 < len(all_months)) or end >= period.end_time.normalize()
        if not complete:
            continue  # 아직 끝나지 않은 달은 순위를 매기지 않는다
        top = rows.sort_values(["Marcap", "Code"], ascending=[False, True]).head(top_n)
        ranks.append(pd.DataFrame({"date": day, "code": top["Code"].to_numpy(), "rank": np.arange(1, len(top) + 1)}))
    if not ranks:
        raise KitError("순위를 만들 데이터가 없습니다.")
    ranks = pd.concat(ranks, ignore_index=True)
    days = sorted(ranks["date"].unique())
    before = [d for d in days if d < start]
    keep = set(before[-1:] + [d for d in days if d >= start])
    universe = ranks[ranks["date"].isin(keep)].reset_index(drop=True)
    members = set(universe["code"])

    # 2) 투자 대상에 한 번이라도 들어간 종목의 기간 내 모든 거래일
    rows = []
    for y in years:
        if y < start.year:
            continue
        d = load(y)
        if d is None or d.empty:
            continue
        rows.append(d[d["Code"].isin(members) & (d["Date"] >= start) & (d["Date"] <= end)])
    if not rows:
        raise KitError("기간 안에 데이터가 없습니다.")
    raw = pd.concat(rows, ignore_index=True)
    raw = raw.sort_values(["Date", "Code"]).drop_duplicates(["Date", "Code"], keep="last")
    prices = pd.DataFrame({
        "date": raw["Date"].dt.normalize().to_numpy(),
        "code": raw["Code"].astype(str).to_numpy(),
        "name": raw["Name"].astype(str).to_numpy(),
        "market": raw["Market"].astype(str).to_numpy(),
        "open": raw["Open"].to_numpy(), "high": raw["High"].to_numpy(), "low": raw["Low"].to_numpy(),
        "close": raw["Close"].to_numpy(), "change": raw["Changes"].to_numpy(),
        "volume": raw["Volume"].to_numpy(), "amount": raw["Amount"].to_numpy(), "shares": raw["Stocks"].to_numpy(),
    })
    for col in INT_COLUMNS:
        prices[col] = np.rint(pd.to_numeric(prices[col], errors="coerce").fillna(0)).astype("int64")
    prices = prices.sort_values(["code", "date"]).reset_index(drop=True)
    return finalize(prices, universe)


def finalize(prices, universe):
    """prices · universe에 맞춰 종목 정보(stocks)를 만든다. 기간을 자를 때도 같은 함수를 쓴다."""
    data_last = prices["date"].max()
    last_rows = prices.sort_values(["code", "date"]).drop_duplicates("code", keep="last").set_index("code")
    first = prices.groupby("code")["date"].min()
    last = last_rows["date"]
    stocks = pd.DataFrame({
        "code": last.index,
        "name": last_rows["name"].to_numpy(),
        "market": last_rows["market"].to_numpy(),
        "first_date": first.reindex(last.index).dt.strftime("%Y-%m-%d").to_numpy(),
        "last_date": last.dt.strftime("%Y-%m-%d").to_numpy(),
        "delisted": (last < data_last).to_numpy(),
    })
    universe = universe.copy()
    universe["date"] = pd.to_datetime(universe["date"])
    return prices, universe.reset_index(drop=True), stocks


# ---------------------------------------------------------------- 쓰기 · 지문

def _parquet_bytes(prices):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ordered = prices[PRICE_COLUMNS].sort_values(["code", "date"])
    table = pa.Table.from_pandas(ordered, preserve_index=False)
    table = table.cast(pa.schema([
        ("date", pa.date32()), ("code", pa.string()), ("name", pa.string()), ("market", pa.string()),
        *[(c, pa.int64()) for c in INT_COLUMNS],
    ])).replace_schema_metadata(None)
    buf = io.BytesIO()
    delta = {c: "DELTA_BINARY_PACKED" for c in ["date", *INT_COLUMNS]}
    pq.write_table(table, buf, compression="zstd", compression_level=9, row_group_size=1 << 24,
                   use_dictionary=["code", "name", "market"], column_encoding=delta, write_statistics=False)
    return buf.getvalue()


def _csv_bytes(df):
    return df.to_csv(index=False, lineterminator="\n").encode("utf-8-sig")


def dataset_bytes(prices, universe, stocks, index_df=None):
    u = universe.copy()
    u["date"] = pd.to_datetime(u["date"]).dt.strftime("%Y-%m-%d")
    out = {
        "prices.parquet": _parquet_bytes(prices),
        "universe.csv": _csv_bytes(u[["date", "code", "rank"]]),
        "stocks.csv": _csv_bytes(stocks),
    }
    if index_df is not None and len(index_df):
        x = index_df[["date", "name", "close"]].copy()
        x["date"] = pd.to_datetime(x["date"]).dt.strftime("%Y-%m-%d")
        x["close"] = pd.to_numeric(x["close"], errors="coerce").round(2)
        x = x.dropna().drop_duplicates(["date", "name"], keep="last").sort_values(["name", "date"])
        out["index.csv"] = _csv_bytes(x)
    return out


def fingerprint(files):
    """prices · universe · stocks 세 파일로 데이터 지문(8자리)을 만든다. 지수 파일은 빼고 계산한다."""
    h = hashlib.sha256()
    for name in ("prices.parquet", "universe.csv", "stocks.csv"):
        h.update(sha256_bytes(files[name]).encode())
    return h.hexdigest()[:8]


def make_manifest(files, prices, universe, stocks, top_n, note=""):
    return {
        "kind": "stock-ai-kit-data",
        "version": 2,
        "created_at_kst": now_kst().strftime("%Y-%m-%d %H:%M"),
        "source": "FinanceData/marcap (한국거래소 일별 데이터)",
        "start": prices["date"].min().strftime("%Y-%m-%d"),
        "end": prices["date"].max().strftime("%Y-%m-%d"),
        "top_n": int(top_n),
        "codes": int(prices["code"].nunique()),
        "delisted": int(stocks["delisted"].sum()),
        "months": int(universe["date"].nunique()),
        "rows": int(len(prices)),
        "files": {name: sha256_bytes(b) for name, b in files.items()},
        "fingerprint": fingerprint(files),
        "note": note,
    }


def write_dataset(folder, files, manifest):
    folder = folder_of(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES[:-1]:
        p = folder / name
        if name in files:
            p.write_bytes(files[name])
        elif p.exists():
            p.unlink()
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- 받기

def _index_frame(start, end, log):
    frames = []
    for name in sources.INDEXES:
        try:
            frames.append(sources.get_index(name, start, end))
        except Exception as e:
            warn(f"{name} 지수를 받지 못했습니다: {type(e).__name__}")
    return pd.concat(frames, ignore_index=True) if frames else None


def download(cfg, start=None, end=None, folder=None, top_n=None, refresh=False, log=print):
    """원천 데이터를 받아 표준 데이터를 만든다."""
    start = pd.Timestamp(start) if start else cfg.data_start
    end = pd.Timestamp(end) if end else pd.Timestamp(now_kst().date())
    top_n = int(top_n or cfg.top_n)
    if start.year < MARCAP_FIRST_YEAR:
        raise KitError(f"원천 데이터는 {MARCAP_FIRST_YEAR}년부터 있습니다.")
    years = list(range(max(MARCAP_FIRST_YEAR, start.year - 1), end.year + 1))
    log(f"원천 데이터 {years[0]}~{years[-1]}년 ({len(years)}개 파일) 확인 중. 처음에는 연도당 10~25MB를 받습니다.")
    for y in years:
        fetch_marcap(y, refresh=refresh, log=log)
    log(f"표준 데이터를 만듭니다: {start.date()} ~ {end.date()}, 매달 시가총액 상위 {top_n}종목")
    prices, universe, stocks = build_dataset(read_marcap, years, start, end, top_n)
    index_df = _index_frame(start, end, log)
    files = dataset_bytes(prices, universe, stocks, index_df)
    manifest = make_manifest(files, prices, universe, stocks, top_n)
    write_dataset(folder, files, manifest)
    return manifest


# ---------------------------------------------------------------- 묶기 · 풀기 · 확인

def read_dataset(folder=None, check_only=False):
    folder = folder_of(folder)
    path = folder / "prices.parquet"
    if not path.exists():
        raise KitError(
            f"{folder}에 데이터가 없습니다. 진행자가 나눠 준 zip이 있으면 'uv run kit data unpack <파일>', "
            "없으면 'uv run kit data download'를 실행해 주세요."
        )
    if check_only:
        return None
    prices = pd.read_parquet(path)
    prices["date"] = pd.to_datetime(prices["date"])
    prices["code"] = prices["code"].astype(str)
    universe = pd.read_csv(folder / "universe.csv", dtype={"code": str}, encoding="utf-8-sig", parse_dates=["date"])
    stocks = pd.read_csv(folder / "stocks.csv", dtype={"code": str}, encoding="utf-8-sig")
    index_path = folder / "index.csv"
    index_df = pd.read_csv(index_path, encoding="utf-8-sig") if index_path.exists() else None
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return prices, universe, stocks, index_df, manifest


def cut_dataset(prices, universe, end):
    """end 날짜까지만 남긴다. 같은 시작일 · end로 새로 만든 데이터와 똑같아진다."""
    end = pd.Timestamp(end)
    p = prices[prices["date"] <= end]
    u = universe[pd.to_datetime(universe["date"]) <= end]
    if len(u):
        last = pd.Timestamp(u["date"].max())
        month_end = last.to_period("M").end_time.normalize()
        if last.to_period("M") == end.to_period("M") and end < month_end:
            u = u[pd.to_datetime(u["date"]) < last]  # 끝나지 않은 달의 순위는 뺀다 (새로 만들 때와 같은 규칙)
    p = p[p["code"].isin(set(u["code"]))].sort_values(["code", "date"]).reset_index(drop=True)
    return finalize(p, u)


def pack(cfg, end=None, folder=None, out=None):
    """참가자에게 나눠 줄 zip을 만든다. 기본은 연구 기간 끝까지."""
    end = pd.Timestamp(end) if end else cfg.research_end
    prices, universe, stocks, index_df, old = read_dataset(folder)
    prices, universe, stocks = cut_dataset(prices, universe, end)
    if index_df is not None:
        index_df = index_df[pd.to_datetime(index_df["date"]) <= end]
    files = dataset_bytes(prices, universe, stocks, index_df)
    manifest = make_manifest(files, prices, universe, stocks, old.get("top_n", cfg.top_n), note=f"pack end={end.date()}")
    out = Path(out) if out else OUTPUTS / "share" / f"stock-ai-kit-data_{manifest['start']}_{manifest['end']}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, b in files.items():
            z.writestr(f"data/{name}", b)
        z.writestr("data/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return out, manifest


def unpack(zip_path, folder=None):
    """진행자가 나눠 준 데이터 zip을 data/에 푼다."""
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise KitError(f"파일이 없습니다: {zip_path}")
    folder = folder_of(folder)
    folder.mkdir(parents=True, exist_ok=True)
    found = set()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = Path(info.filename).name
            if info.is_dir() or name not in FILES:
                continue
            (folder / name).write_bytes(z.read(info))
            found.add(name)
    if "prices.parquet" not in found:
        raise KitError("zip 안에 prices.parquet이 없습니다. 진행자가 나눠 준 데이터 파일이 맞는지 확인해 주세요.")
    for name in set(FILES[:-1]) - found:
        if (folder / name).exists():
            (folder / name).unlink()  # 이전 데이터의 남은 파일 정리
    return verify(folder)


def verify(folder=None):
    """폴더의 파일이 manifest.json에 적힌 지문과 같은지 확인한다."""
    folder = folder_of(folder)
    mpath = folder / "manifest.json"
    if not (folder / "prices.parquet").exists():
        return False, "prices.parquet이 없습니다."
    if not mpath.exists():
        return False, "manifest.json이 없습니다."
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    for name, digest in manifest.get("files", {}).items():
        p = folder / name
        if not p.exists() or sha256_file(p) != digest:
            return False, f"{name}이(가) 받았을 때와 다릅니다 (수정되었거나 손상됨)."
    return True, manifest


def describe(folder=None):
    folder = folder_of(folder)
    mpath = folder / "manifest.json"
    if not (folder / "prices.parquet").exists() or not mpath.exists():
        return None
    return json.loads(mpath.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 불러오기 (수정주가 계산)

def _segments(ci):
    """(종목, 날짜) 순으로 정렬된 행에서 종목별 [시작, 끝) 구간."""
    b = np.flatnonzero(np.r_[True, ci[1:] != ci[:-1], True]) if len(ci) else np.array([0])
    return list(zip(b[:-1], b[1:]))


def _adjust_arrays(date, ci, close, change, anchor):
    """수정 비율(배열). 수정주가 = 실제 가격 × 비율. 행은 (종목, 날짜) 순으로 정렬돼 있어야 한다.

    거래소 기준가(종가 - 전일 대비)로 하루 수익률을 이어 붙이고, anchor 날짜 이전 마지막 거래일
    (그 전에 거래가 없으면 그 종목 첫 거래일)의 수정주가가 실제 가격과 같도록 맞춘다.
    시작일이 같으면 데이터의 끝 날짜가 달라도 같은 값이 나온다.
    """
    close = close.astype("float64")
    base = close - change.astype("float64")
    before = date <= np.datetime64(pd.Timestamp(anchor), "ns")
    factor = np.empty(len(close))
    with np.errstate(divide="ignore", invalid="ignore"):
        for a, b in _segments(ci):
            c = close[a:b]
            prev = np.r_[np.nan, c[:-1]]
            g = np.where(base[a:b] > 0, c / base[a:b], np.nan)
            g = np.where(np.isfinite(g) & (g > 0), g, c / prev)
            g[0] = 1.0
            g = np.where(np.isfinite(g) & (g > 0), g, 1.0)
            cum = np.multiply.accumulate(g)
            bb = before[a:b]
            r = (len(bb) - 1 - int(np.argmax(bb[::-1]))) if bb.any() else 0
            f = (cum * c[r] / cum[r]) / np.where(c > 0, c, np.nan)
            ok = np.isfinite(f)
            if not ok.all():  # 종가가 0인 날은 앞의 비율을 그대로 쓴다
                pos = np.where(ok, np.arange(len(f)), 0)
                np.maximum.accumulate(pos, out=pos)
                f = np.where(ok[pos], f[pos], 1.0)
            factor[a:b] = f
    return factor


def _read_arrays(path):
    """prices.parquet을 숫자 배열로 읽는다 (문자열은 사전 번호로).

    열을 하나씩 읽고 바로 압축 해제 버퍼를 돌려줘서, 노트북에서도 메모리를 적게 쓴다.
    """
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    pool = pa.default_memory_pool()
    pf = pq.ParquetFile(path, read_dictionary=["code", "name", "market"])
    out = {}
    for f in ("date", "code", "name", "market", *Panel.RAW_FIELDS, "change"):
        col = pf.read(columns=[f]).column(0)
        if f == "date":
            out[f] = pc.cast(col, pa.timestamp("ns")).to_numpy()
        elif f in ("code", "name", "market"):
            col = col.unify_dictionaries().combine_chunks()
            out[f] = (col.indices.to_numpy(zero_copy_only=False).astype(np.int32),
                      [str(x) for x in col.dictionary.to_pylist()])
        else:
            out[f] = col.to_numpy()
        del col
        pool.release_unused()
    return out


def _arrays_from_frame(df):
    out = {"date": pd.to_datetime(df["date"]).to_numpy().astype("datetime64[ns]")}
    for f in ("code", "name", "market"):
        vals, uniq = pd.factorize(df[f].astype(str))
        out[f] = (vals.astype(np.int32), [str(x) for x in uniq])
    for f in Panel.RAW_FIELDS + ("change",):
        out[f] = df[f].to_numpy()
    return out


class Panel:
    """날짜 × 종목 표 묶음. 엔진과 전략이 쓰는 형태. 필요한 표만 그때 만든다."""

    PRICE_FIELDS = ("open", "high", "low", "close")
    RAW_FIELDS = ("open", "high", "low", "close", "volume", "amount", "shares")

    def __init__(self, prices, universe, stocks, anchor, _shared=None, _end=None):
        if _shared is None:
            arrays = prices if isinstance(prices, dict) else _arrays_from_frame(prices)
            _shared = self._prepare(arrays, universe, stocks, anchor)
        self._s = _shared
        self._end = len(_shared["dates"]) - 1 if _end is None else _end
        self.dates = _shared["dates"][: self._end + 1]
        self.codes = _shared["codes"]
        info = _shared["stocks"].set_index("code")
        self.names = info["name"].to_dict()
        self.markets = info["market"].to_dict()

    @staticmethod
    def _prepare(a, universe, stocks, anchor):
        code_idx, code_labels = a["code"]
        codes = sorted(code_labels)
        pos = np.searchsorted(np.asarray(codes), np.asarray(code_labels))
        ci = pos[code_idx].astype(np.int32)
        date = a["date"]
        order = np.lexsort((date, ci))
        if not (order == np.arange(len(order))).all():
            ci, date = ci[order], date[order]
            a = {k: ((v[0][order], v[1]) if isinstance(v, tuple) else (v[order] if k != "date" else v))
                 for k, v in a.items()}
        dates = pd.DatetimeIndex(np.unique(date))
        di = dates.searchsorted(date).astype(np.int32)
        raw = {f: a[f] for f in Panel.RAW_FIELDS}
        adj = _adjust_arrays(date, ci, raw["close"], a["change"], anchor)
        first = np.r_[True, ci[1:] != ci[:-1]]
        hist = {}
        for field in ("name", "market"):
            vals, labels = a[field]
            changed = np.flatnonzero(first | np.r_[True, vals[1:] != vals[:-1]])
            h = {}
            for k in changed:
                c = codes[ci[k]]
                h.setdefault(c, ([], []))
                h[c][0].append(date[k])
                h[c][1].append(labels[vals[k]])
            hist[field] = {c: (np.array(d, dtype="datetime64[ns]"), n) for c, (d, n) in h.items()}
        uni = universe.copy()
        uni["date"] = pd.to_datetime(uni["date"])
        uni["code"] = uni["code"].astype(str)
        return {"dates": dates, "codes": codes, "di": di, "ci": ci, "raw": raw, "adj": adj, "hist": hist,
                "universe": uni, "stocks": stocks, "cache": {}}

    def _wide(self, field):
        s = self._s
        cache = s["cache"]
        if field not in cache:
            raw, adj = s["raw"], s["adj"]
            if field in self.PRICE_FIELDS:
                v = raw[field].astype("float64")
                v[v <= 0] = np.nan
                v *= adj
            elif field == "volume":
                v = raw["volume"].astype("float64") / adj
            elif field == "price":
                v = raw["close"].astype("float64")
                v[v <= 0] = np.nan
            elif field == "marcap":
                v = raw["close"].astype("float64") * raw["shares"].astype("float64")
            else:
                v = raw[field].astype("float64")
            arr = np.full((len(s["dates"]), len(s["codes"])), np.nan)
            arr[s["di"], s["ci"]] = v
            cache[field] = pd.DataFrame(arr, index=s["dates"], columns=s["codes"], copy=False)
        return cache[field].iloc[: self._end + 1]

    def _member_full(self):
        cache = self._s["cache"]
        if "member" not in cache:
            dates, codes = self._s["dates"], self.codes
            col = {c: k for k, c in enumerate(codes)}
            m = np.zeros((len(dates), len(codes)), dtype=bool)
            u = self._s["universe"]
            ranking_days = sorted(u["date"].unique())
            for j, day in enumerate(ranking_days):
                lo = int(dates.searchsorted(pd.Timestamp(day)))
                hi = int(dates.searchsorted(pd.Timestamp(ranking_days[j + 1]))) if j + 1 < len(ranking_days) else len(dates)
                if hi <= 0 or lo >= len(dates):
                    continue
                ks = [col[c] for c in u.loc[u["date"] == day, "code"] if c in col]
                m[max(lo, 0):hi, ks] = True
            cache["member"] = pd.DataFrame(m, index=dates, columns=codes)
        return cache["member"]

    open = property(lambda self: self._wide("open"))
    high = property(lambda self: self._wide("high"))
    low = property(lambda self: self._wide("low"))
    close = property(lambda self: self._wide("close"))
    volume = property(lambda self: self._wide("volume"))
    amount = property(lambda self: self._wide("amount"))
    marcap = property(lambda self: self._wide("marcap"))
    price = property(lambda self: self._wide("price"))
    member = property(lambda self: self._member_full().iloc[: self._end + 1])

    def _on(self, field, code, day):
        h = self._s["hist"][field].get(code)
        if h is None:
            return code if field == "name" else ""
        k = int(np.searchsorted(h[0], np.datetime64(pd.Timestamp(day), "ns"), side="right")) - 1
        return h[1][max(k, 0)]

    def name_on(self, code, day):
        """그날 기준 종목 이름 (이름이 바뀐 종목은 그때 이름)."""
        return self._on("name", code, day)

    def market_on(self, code, day):
        """그날 기준 시장 (코스닥에서 코스피로 옮긴 종목은 그때 시장)."""
        return self._on("market", code, day)

    def until(self, i):
        """i번째 날까지만 보이는 Panel (미래 데이터 검사용)."""
        return Panel(None, None, None, None, _shared=self._s, _end=i)


def load_panel(cfg, folder=None):
    folder = folder_of(folder)
    read_dataset(folder, check_only=True)
    prices = _read_arrays(folder / "prices.parquet")
    universe = pd.read_csv(folder / "universe.csv", dtype={"code": str}, encoding="utf-8-sig", parse_dates=["date"])
    stocks = pd.read_csv(folder / "stocks.csv", dtype={"code": str}, encoding="utf-8-sig")
    return Panel(prices, universe, stocks, cfg.adjust_anchor)


def load_index(dates, folder=None):
    """지수 종가를 날짜에 맞춰 돌려준다 (없으면 빈 표)."""
    path = folder_of(folder) / "index.csv"
    if not path.exists():
        return pd.DataFrame(index=dates)
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["date"] = pd.to_datetime(df["date"])
    wide = df.pivot(index="date", columns="name", values="close").sort_index()
    return wide.reindex(dates).ffill()


# ---------------------------------------------------------------- 분봉 쌓기

def save_minute(code, interval="1m", days=8, market=None):
    """분봉을 받아 data/minute/<code>_<interval>.csv에 이어 붙인다 (겹치는 시각은 새 값으로)."""
    df = sources.get_minute(code, interval=interval, days=days, market=market)
    MINUTE.mkdir(parents=True, exist_ok=True)
    path = MINUTE / f"{str(code).zfill(6)}_{interval}.csv"
    if path.exists():
        old = pd.read_csv(path, dtype={"code": str}, parse_dates=["datetime"])
        df = pd.concat([old, df], ignore_index=True)
    if len(df):
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.drop_duplicates(["datetime"], keep="last").sort_values("datetime")
        df.to_csv(path, index=False, lineterminator="\n", date_format="%Y-%m-%d %H:%M:%S")
    return path, len(df)
